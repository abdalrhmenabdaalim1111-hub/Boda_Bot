# Boda Bot Subscription Gate Policy

**Status:** Draft / Enforcement Policy

## 1. Core Principles
- **Transparency**: Users must be explicitly informed why they need to join channels.
- **Fairness**: Gate mechanism must not be deceptive or exploit user trust.
- **Fail-Open**: System failures (e.g., Telegram error) must not block users permanently.
- **No Abuse**: Channels must not be used for deceptive lists or messaging without consent.

## 2. Prohibited Practices
- **Deceptive Verification**: Do not frame the gate as "verification you are human" or "prove you are not a bot" — this is deceptive and exploits user trust.
- **Deceptive Wording**: Do not use "guaranteed" or medical/financial claims that haven't been neutrally verified.
- **Forced Actions**: No auto-adding users to channels or messaging them from collected lists.

## 3. Compliance Guardrails (Enforced)
- **Honest Copy**: The dashboard will run text content through a compliance checker (`gate._compliance_check`) before applying.
  - Risks (Medical, Financial, Guarantee) trigger a mandatory review warning with neutral suggestions.
  - Verification prompts must accurately describe the action ("Join channel to use this bot").

## 4. Operational Requirements
- **Checker Bot Administration**: The checker bot must have admin rights in all gate channels to verify membership.
- **Health Monitoring**: Regular health checks to ensure channels are reachable and bot remains admin.
- **User Privacy**: Event tracking uses SHA256 hashed user IDs (`_user_id_hash`) to protect identity in funnel analytics.

*Failure to comply with this policy will trigger admin alerts and system lockdown for the offending bot.*