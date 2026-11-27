# Canary Swarm v3 Palette Key

Flat, modern light-mode palette built for the 3-cage demo (`tokens.css`).

## Surfaces & Ink

| Token | Value | Role |
| --- | --- | --- |
| `--sp-white` | `#FFFFFF` | Primary page & cage dome background |
| `--sp-paper` | `#F8F8F6` | Cage body ground & subtle panels |
| `--sp-rule` | `#E5E2DC` | Hairline rules & subtle borders |
| `--sp-ink` | `#161412` | Wordmark, headings, primary text |
| `--sp-ink-soft` | `rgba(22, 20, 18, 0.62)` | Secondary labels & telemetry |
| `--sp-ink-faint` | `rgba(22, 20, 18, 0.42)` | Tertiary metadata & timestamps |

## Brand, Cage & Canary

| Token | Value | Role |
| --- | --- | --- |
| `--sp-gold` | `#C99A2E` | Flat gold cage arches, frames, top rings, perch wires, primary CTA |
| `--sp-gold-2` | `#D4A73A` | Secondary gold highlights & completion rule |
| `--sp-yellow` | `#F5D018` | Canary body fill |
| `--sp-yellow-hi` | `#FACC15` | Canary wing & feather accent |
| `--sp-yellow-belly` | `#FDE68A` | Soft flat canary belly tint |
| `--sp-beak` | `#E8943A` | Canary beak |
| `--sp-wood` | `#9C6B3F` | Hanging wooden perch base |
| `--sp-wood-hi` | `#B5835A` | Hanging wooden perch top highlight |

## Semantic Test States

| State | Solid | Text / Button | Soft Tint | Usage |
| --- | --- | --- | --- | --- |
| **Pass / Good** | `--sp-green` `#16A34A` | `--sp-green-text` `#166534` / `--sp-green-btn` `#15803D` | `--sp-green-soft` `#ECFDF5` | Passing tests, `APPROVE` button, `SHIP IT` stamp |
| **Caution / Hold** | `--sp-amber` `#D97706` (`--sp-amber-2` `#F59E0B`) | `--sp-amber-text` `#92400E` | `--sp-amber-soft` `#FFFBEB` | `AWAITING APPROVAL`, human-in-the-loop hold |
| **Fail / Contained** | `--sp-red` `#DC2626` (`--sp-red-deep` `#E52521`) | `--sp-red-text` `#991B1B` | `--sp-red-soft` `#FEF2F2` | `UI BUGS FOUND`, red bounding boxes, `CONTAINED · WIPED`, `DO NOT SHIP` |

## Typography

- **Display & UI:** `Poppins` (weights 400–900, self-hosted in `fonts/`)
- **Telemetry & Labels:** `IBM Plex Mono` (weights 400–700, self-hosted in `fonts/`)
