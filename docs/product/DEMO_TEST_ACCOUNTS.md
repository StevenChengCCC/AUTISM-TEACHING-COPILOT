# Demo test accounts

No passwords or live tokens belong in this repository.

Use a small set of administrator-created Cognito users containing synthetic data only:

| Purpose | Suggested synthetic identity | Organization | Group |
| --- | --- | --- | --- |
| Primary teacher | `teacher-demo@example.test` | `demo-organization` | none |
| Demo administrator | `admin-demo@example.test` | `demo-organization` | `lesson-kit-admins` |
| Isolation check | `teacher-isolation@example.test` | `isolation-organization` | none |

Actual addresses may differ when email delivery is required. Keep the account mapping and temporary passwords in an approved team password manager, not GitHub, Slack, screenshots, build logs, or frontend environment variables.

Before each demo, verify accounts are enabled, custom `organization_id` is correct, callback URLs are current, and temporary-password reset is complete. After the demo window, revoke sessions and disable or delete temporary accounts according to the team retention policy.

