from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

import pandas as pd


@dataclass
class Recommendation:
    action: str
    action_type: str
    channel: str
    priority: str
    score: float
    reason: str
    expected_goal: str
    automation_eligible: bool
    offer_percent: int = 0


def build_customer_features(df: pd.DataFrame) -> pd.DataFrame:
    required = {"CustomerID", "InvoiceNo", "InvoiceDate", "Quantity", "UnitPrice"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    work = df.copy()
    work = work.dropna(subset=["CustomerID", "InvoiceDate"])
    work["InvoiceDate"] = pd.to_datetime(work["InvoiceDate"], errors="coerce")
    work["Quantity"] = pd.to_numeric(work["Quantity"], errors="coerce")
    work["UnitPrice"] = pd.to_numeric(work["UnitPrice"], errors="coerce")
    work = work.dropna(subset=["InvoiceDate", "Quantity", "UnitPrice"])
    work = work[work["Quantity"] > 0]
    work = work[work["UnitPrice"] >= 0]
    work["TotalPrice"] = work["Quantity"] * work["UnitPrice"]
    if work.empty:
        raise ValueError("No valid transactions remain after cleaning.")

    reference_date = work["InvoiceDate"].max()
    grouped = work.groupby("CustomerID")
    product_agg = ("StockCode", "nunique") if "StockCode" in work.columns else ("InvoiceNo", "nunique")
    features = grouped.agg(
        PurchaseFrequency=("InvoiceNo", "nunique"),
        TotalQuantity=("Quantity", "sum"),
        TotalSpend=("TotalPrice", "sum"),
        LastPurchaseDate=("InvoiceDate", "max"),
        FirstPurchaseDate=("InvoiceDate", "min"),
        UniqueProducts=product_agg,
    ).reset_index()

    features["Recency"] = (reference_date - features["LastPurchaseDate"]).dt.days.clip(lower=0)
    features["CustomerTenureDays"] = (features["LastPurchaseDate"] - features["FirstPurchaseDate"]).dt.days.clip(lower=0)
    features["AverageOrderValue"] = features["TotalSpend"] / features["PurchaseFrequency"].replace(0, 1)

    gaps = (
        work[["CustomerID", "InvoiceDate"]]
        .drop_duplicates()
        .sort_values(["CustomerID", "InvoiceDate"])
        .assign(GapDays=lambda x: x.groupby("CustomerID")["InvoiceDate"].diff().dt.days)
    )
    gap_stats = gaps.groupby("CustomerID")["GapDays"].agg(
        AveragePurchaseGap="mean", MaximumPurchaseGap="max"
    ).reset_index()
    features = features.merge(gap_stats, on="CustomerID", how="left")
    features[["AveragePurchaseGap", "MaximumPurchaseGap"]] = features[["AveragePurchaseGap", "MaximumPurchaseGap"]].fillna(0)

    features["ChurnRiskScore"] = _risk_score(features)
    features["ChurnRisk"] = pd.cut(
        features["ChurnRiskScore"], bins=[-0.01, 0.33, 0.66, 1.0], labels=["LOW", "MEDIUM", "HIGH"]
    ).astype(str)
    features["Segment"] = _segment_customers(features)
    return features


def _risk_score(f: pd.DataFrame) -> pd.Series:
    recency = (f["Recency"] / max(float(f["Recency"].quantile(0.95)), 1)).clip(0, 1)
    freq = 1 - (f["PurchaseFrequency"] / max(float(f["PurchaseFrequency"].quantile(0.95)), 1)).clip(0, 1)
    spend = 1 - (f["TotalSpend"] / max(float(f["TotalSpend"].quantile(0.95)), 1)).clip(0, 1)
    gap = (f["AveragePurchaseGap"] / max(float(f["AveragePurchaseGap"].quantile(0.95)), 1)).clip(0, 1)
    return (0.45 * recency + 0.25 * freq + 0.15 * spend + 0.15 * gap).clip(0, 1)


def _segment_customers(f: pd.DataFrame) -> pd.Series:
    spend_q = f["TotalSpend"].quantile([0.33, 0.66]).tolist()
    freq_q = f["PurchaseFrequency"].quantile(0.66)
    rec_q = f["Recency"].quantile(0.66)

    def label(row: pd.Series) -> str:
        if row.TotalSpend >= spend_q[1] and row.PurchaseFrequency >= freq_q:
            return "VIP / Loyal"
        if row.Recency > rec_q:
            return "At-Risk / Occasional"
        if row.PurchaseFrequency >= freq_q:
            return "Loyal Regular"
        return "Average Customer"

    return f.apply(label, axis=1)


def recommend(row: pd.Series) -> Recommendation:
    risk = float(row.get("ChurnRiskScore", 0))
    spend = float(row.get("TotalSpend", 0))
    recency = float(row.get("Recency", 0))
    frequency = float(row.get("PurchaseFrequency", 0))
    segment = str(row.get("Segment", "Average Customer"))
    value_reference = max(float(row.get("ValueReference", spend or 1)), 1)
    value_factor = min(spend / value_reference, 1)
    priority_score = min(100, 100 * (0.65 * risk + 0.35 * value_factor))

    if risk >= 0.72 and segment == "VIP / Loyal":
        return Recommendation(
            "Personalized VIP retention offer", "OFFER", "Email", "CRITICAL", priority_score,
            "High churn risk combined with high customer value and strong purchase history.",
            "Protect a valuable relationship with a targeted incentive.", True, 15,
        )
    if risk >= 0.72:
        return Recommendation(
            "Re-engagement campaign + personalized offer", "EMAIL", "Email", "HIGH", priority_score,
            f"The customer has high inactivity risk ({recency:.0f} days since last purchase).",
            "Bring the customer back with a targeted, low-friction message or offer.", True, 10,
        )
    if risk >= 0.50 and frequency >= 3:
        return Recommendation(
            "Loyalty reward", "OFFER", "Email", "MEDIUM", priority_score,
            "The customer is engaged but showing enough risk to justify a loyalty nudge.",
            "Encourage the next purchase and strengthen repeat behavior.", True, 5,
        )
    if risk >= 0.35:
        return Recommendation(
            "Personalized product recommendation", "RECOMMENDATION", "Email", "MEDIUM", priority_score,
            "The customer has moderate risk; relevance is preferable to a broad discount.",
            "Increase engagement using products related to previous purchases.", False, 0,
        )
    return Recommendation(
        "Continue normal engagement", "MONITOR", "Dashboard", "LOW", priority_score,
        "Current behavior does not indicate an urgent retention problem.",
        "Avoid unnecessary incentives while maintaining the relationship.", False, 0,
    )


def add_recommendations(features: pd.DataFrame) -> pd.DataFrame:
    value_reference = max(float(features["TotalSpend"].quantile(0.75)), 1)
    work = features.copy()
    work["ValueReference"] = value_reference
    recs = work.apply(recommend, axis=1)
    work["RecommendedAction"] = [r.action for r in recs]
    work["ActionType"] = [r.action_type for r in recs]
    work["Channel"] = [r.channel for r in recs]
    work["Priority"] = [r.priority for r in recs]
    work["RecommendationScore"] = [r.score for r in recs]
    work["RecommendationReason"] = [r.reason for r in recs]
    work["ExpectedGoal"] = [r.expected_goal for r in recs]
    work["AutomationEligible"] = [r.automation_eligible for r in recs]
    work["OfferPercent"] = [r.offer_percent for r in recs]
    return work.drop(columns=["ValueReference"])
