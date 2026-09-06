# CustomerIQ — Intelligent Retention & Action Platform

A Streamlit customer analytics and recommendation prototype that goes one step beyond a dashboard: it creates customer-level features, estimates churn risk, recommends a retention action, and provides an Action Center to execute eligible actions and maintain an audit trail.

## What is new
- ⚡ Action Center with Execute Action buttons
- 🤖 Automation mode for eligible high-risk actions
- 👤 Customer 360 with action context
- 📜 Action History / audit trail
- 📥 CSV export of recommendations and action history
- Explainable recommendation reason + expected goal

## Important demo note
The current action executor is **demo-safe**: it records an action as executed inside the Streamlit session. It does not send real email or create real external tasks. This is intentional until an email/CRM provider is connected.

## Run locally
```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Recommended next integration
Connect `execute action` to an email provider (SMTP/SendGrid/Mailgun), CRM, or notification service. Store action history in PostgreSQL instead of Streamlit session state, then capture outcomes such as email opened, offer redeemed, and purchase after intervention.

## Current ML honesty
The churn risk is a transparent behavioral baseline, not a trained supervised churn model. A later phase can replace it with a real churn classifier and use predicted churn probability in the action policy.
