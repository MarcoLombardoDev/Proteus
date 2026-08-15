# Commercial Licence

**Proteus — Rebranding Tool**
Version 1.0, August 2026

Proteus is dual-licensed. It is available under the
[GNU Affero General Public License v3.0](LICENSE) at no cost, and under the commercial
terms set out in this document for those who cannot accept the AGPL's obligations.

Both licences cover the same software. There is no crippled edition, no feature held back
behind a paywall, and no licence check in the code. What you buy is **permission**, not
functionality.

---

## 1. Do you actually need this?

Most people do not. Read this section before reading the price list.

| What you want to do | Licence you need |
|---|---|
| Use Proteus inside your company, unmodified, however many people, however many machines | **AGPL — free.** Nothing to buy, nothing to declare. |
| Modify it for your own internal use and keep the changes to yourself | **AGPL — free.** The AGPL only asks for source when you *convey* the software or let others interact with it over a network. |
| Publish a fork, or ship a modified version to someone else | **AGPL — free**, provided you release your modified source under AGPL-3.0. |
| Ship Proteus, or code derived from it, inside a **closed-source product** | **Commercial** |
| Run a modified Proteus as a **hosted or SaaS service** other people use, without publishing your source | **Commercial** |
| Redistribute it to your customers under **your own name or branding** | **Commercial** |
| You are legally required to avoid copyleft dependencies, and need it in writing | **Commercial** |

**Internal business use of the unmodified tool is free, permanently, for organisations of
any size.** A vendor telling you otherwise about an AGPL project is mistaken. Buy a
commercial licence when the AGPL's *distribution* terms are the problem — not simply
because you are a company.

If you are unsure which column you are in, ask before you buy. See §9.

---

## 2. What the commercial licence grants

Subject to payment and to the limits of the tier purchased, the Project Owner grants a
non-exclusive, non-transferable, worldwide licence to:

1. use, copy and modify Proteus;
2. incorporate it, in whole or in part, into your own products and services;
3. distribute it in **binary or source form as part of your product**, without any
   obligation to publish your own source code;
4. deploy it as part of a network-accessible service without triggering AGPL section 13;
5. sublicense these rights to your end users **solely as part of your product**, and not as
   a standalone competing tool.

The licence covers the Project Owner's copyright in Proteus. It does not grant rights to
the third-party components listed in §7, which carry their own permissive terms.

---

## 3. Price list

All prices are in **EUR, excluding VAT**, per **licensee organisation** (the legal entity
and its majority-owned subsidiaries). Seats are never counted — you are not billed per
developer or per installation.

| Tier | Price | Who it is for | Grants |
|---|---:|---|---|
| **Community** | **€0** | Everyone | AGPL-3.0. Unlimited internal use. |
| **Startup** | **€450 / year** | Fewer than 10 employees **and** under €1M annual revenue | One product or service. Closed-source embedding. |
| **Business** | **€1,900 / year** | Companies past the Startup thresholds | Up to three products or services. Hosted deployment. Email support, 5 business days. |
| **Enterprise** | **€5,900 / year** | Unlimited scope | Unlimited products, SaaS and redistribution. Email support, 2 business days. Written answers to procurement and legal questionnaires. |
| **OEM / perpetual** | **from €14,000** one-off | Rebranding it as your own, or needing a licence that cannot lapse | Perpetual, irrevocable rights for one named product line. Priced per case. |

### Optional extras

| | Price |
|---|---:|
| Support contract for **AGPL** users (no licence change, just help) | €600 / year |
| Priority feature development | €900 / day |
| White-label build: your name, your icon, your strings | €2,500 one-off |
| On-site or remote onboarding, half day | €700 |

### What a subscription actually buys

- **Perpetual fallback.** Every version released while your subscription is active stays
  licensed to you **forever**, under these terms. Let the subscription lapse and you keep
  running what you had; you simply stop receiving new versions under commercial terms.
- **No retroactive charge.** Renewals are priced at the rate in force when you first
  bought, for as long as you renew without a gap.
- **Cancel any time.** No notice period, no auto-renewal trap. An invoice is issued for
  each term; not paying it ends the subscription.

---

## 4. How to buy

1. **Ask.** Open a GitHub issue titled `Commercial licence enquiry` on the
   [Proteus repository](https://github.com/MarcoLombardoDev/Proteus), or write to the
   address in §9. Say what you intend to build and roughly how big your organisation is.
2. **Confirm the tier.** You get a written statement of which tier applies and why, so
   there is no ambiguity later.
3. **Invoice.** Issued in EUR, payable by bank transfer within 30 days.
4. **Certificate.** On payment you receive a signed licence certificate naming your
   organisation, the tier, the term and the covered products. That certificate — not a
   key file — is the licence.

There is **no licence key, no activation, no phone-home**. The software behaves identically
whether or not you have paid. This is deliberate: a tool that overwrites files on a
production share should not also contain a network client or a kill switch. Compliance is
contractual and self-declared; there is no audit clause.

---

## 5. Term, warranty and liability

- **Term.** Annual, from the invoice date, unless the tier says otherwise.
- **Updates.** Included for the duration of the term.
- **Warranty.** Proteus is provided **as is**. No warranty of merchantability, fitness for
  a particular purpose, or non-infringement is given. Read the
  [Disclaimer](README.md#disclaimer) — this tool overwrites files in place.
- **Liability.** The Project Owner's total aggregate liability under a commercial licence
  is limited to **the fees paid in the twelve months preceding the claim**. Liability is
  not excluded where it cannot lawfully be excluded — death or personal injury caused by
  negligence, fraud, or wilful misconduct.
- **Indemnity.** No IP indemnity is offered at Startup or Business tier. Enterprise and OEM
  licences may include one; ask, and it will be stated in the certificate.
- **Governing law.** Italian law, courts of Milan, unless the certificate names otherwise.

---

## 6. What is *not* included

Stated plainly, so nobody discovers it after paying:

- **No SLA on the software itself.** Support response times are commitments about replying
  to you, not about fixing anything within a window.
- **No hosted service.** Proteus is a desktop application and a command line. There is
  nothing to sign into.
- **No professional services** beyond the extras in §3.
- **No guarantee of future features.** The roadmap is not a contract.
- **No exclusivity.** The same licence is available to your competitors.

---

## 7. Third-party components

A commercial licence covers Proteus itself. Its dependencies are separately licensed, all
under permissive terms compatible with closed-source distribution:

| Component | Licence | Note |
|---|---|---|
| Python, `tkinter` | PSF License | Permissive |
| Pillow | MIT-CMU (HPND) | Permissive |
| ttkbootstrap | MIT | Optional dependency |
| PyInstaller | GPL-2.0 **with bootloader exception** | The exception exists precisely to allow proprietary frozen applications |

Proteus reads and writes Office packages using the Python standard library alone; no
Office-format library is bundled or required at runtime. `python-docx`, `python-pptx` and
`openpyxl` are test-only dependencies and are not shipped.

Verify these against the versions you actually ship. They are listed here in good faith,
current as at the version of this document, and are not a legal opinion.

---

## 8. Contributors

Contributions are accepted under the [CLA](CLA.md), which grants the Project Owner the
right to license contributed code under both AGPL-3.0 and commercial terms. That grant is
what makes this dual-licensing model possible: without it, a single contributed patch would
make commercial licensing impossible for everyone.

Contributors keep the copyright in their work. They are granted a perpetual, royalty-free
commercial licence to Proteus for their own use, as thanks.

---

## 9. Contact

Commercial licensing enquiries: open an issue titled `Commercial licence enquiry` on the
[Proteus repository](https://github.com/MarcoLombardoDev/Proteus/issues).

<!-- Replace with a real address before publishing a price list you intend to honour:
     a public issue is a poor channel for a purchase order. -->
Direct enquiries: _(licensing address to be published)_

---

*This document is a commercial offer, not legal advice, and not a substitute for advice
from your own counsel. Prices and terms may change for new purchases; a licence already
issued is governed by the certificate you hold, not by later revisions of this file.*

*Copyright © 2026 Marco Lombardo. Proteus is licensed under AGPL-3.0; commercial licensing
is available under the terms above.*
