Inherits From: ~/.agent/styles/keyring.md

# Project-Specific Overrides: Keyring
- **Service Name**: `shmail_meta`
- **Key Name**: `active_account` (stores the email of the active session).
- **Metadata Store**: Reserved keychain entry for active user email.
- **Discovery**: Query `gmail.getProfile()` to discover the authorized email address post-OAuth.
