# Profiles

Profiles are JSON files with the `.sebx-profile` extension. Files in this folder load automatically when the app starts.

## Bundled profiles

- `weaponcore.sebx-profile`
- `assertive_armaments.sebx-profile`
- `build_vision.sebx-profile`

Enable a profile’s categories in the converter panel the same way you enable built-in categories. Conflicting categories can exist side by side; only turn on combinations that do not map the same block two different ways.

## Add your own (local use)

1. Export from **Profile Editor**, or copy a bundled file and edit it.
2. Place the `.sebx-profile` in this folder.
3. Restart the app or rescan.

Schema:

```json
{
  "name": "WeaponCore Upgrades",
  "author": "Meraby Labs",
  "version": "1.0",
  "description": "Swap vanilla weapons for WeaponCore equivalents",
  "game_version": "1.205+",
  "categories": [
    {
      "name": "WC Turrets",
      "description": "Large-grid turret upgrades",
      "grid_sizes": ["Large"],
      "pairs": [
        ["LargeGatlingTurret", "WC_LargeGatlingTurret"]
      ]
    }
  ]
}
```

Rules:

- Every pair is `[source, target]`.
- No empty values.
- No circular mappings in a category (`A -> B` and `B -> A`).
- No duplicate targets in a category.

You can also share a profile as a Discord payload from the Profile Editor. Mapping needs can be described with the Mapping Request issue form on GitHub; that is a request to Meraby Labs, not an invitation to submit patches.
