# Family Circle Account Logins

Private family reference only. Do not publish or redistribute this file with a public repository.

## Initial Sign-In Credentials

The current starter password for all initial accounts is:

```text
password123
```

| Account | Username | Initial Password | Access |
| --- | --- | --- | --- |
| KJ | `kj` | `password123` | Child dashboard |
| Astoria | `astoria` | `password123` | Child dashboard |
| Saphira | `saphira` | `password123` | Child dashboard |
| Dad | `dad` | `password123` | Full guardian management, balance controls, Teamup settings |
| Mom | `mom` | `password123` | Read-only family progress view |
| GG | `gg` | `password123` | Guardian management and approvals |

## Railway Variables

For the first deployment using the shared temporary password, set:

```text
INITIAL_CHILD_PASSWORD=password123
INITIAL_GUARDIAN_PASSWORD=password123
```

The deployment also has Docker fallback behavior that uses `password123` for first-time seeded accounts when these two variables are not supplied.

## Important Security Note

Because this app contains information about children and family finances, replace `password123` with strong individual passwords before giving anyone the live app URL.
