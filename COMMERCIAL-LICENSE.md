# LevityDash Commercial License (DRAFT TEMPLATE)

> **Draft, not legal advice.** This is a template written for the author to review and have a lawyer check before use. Nothing here is in force until it is finalized, signed by both parties, and the bracketed items are filled in. It is not an offer. The public license for LevityDash remains the GPLv3 (`LICENSE.txt`) until a signed agreement says otherwise.

**What this is for.** The GPLv3 is free for everyone, including companies. A commercial license exists for people who cannot or do not want to meet the GPLv3 conditions, mainly shipping a closed-source product or device that includes LevityDash, or distributing a modified LevityDash without publishing the source of their changes. If you are only running LevityDash, even at a business, you do not need this.

---

## Commercial License Agreement

This Agreement is between **Bryan Neal Garrison** [or: the entity that will hold the rights, to be confirmed] ("**Licensor**") and **[Customer legal name, address]** ("**Licensee**"), effective on **[date]** (the "**Effective Date**").

### 1. Definitions

1.1 **"Software"** means the LevityDash source code, documentation, and binary builds that Licensor publishes at or after the version named in the Order Form, excluding the Excluded Components.

1.2 **"Licensed Product"** means the Licensee product(s) named in the Order Form that include, link to, or are derived from the Software.

1.3 **"Excluded Components"** means (a) third-party components, which stay under their own licenses (see section 6); and (b) the optional Qt Canvas Painter renderer (`lib/ui/frontends/PySide/canvas/` and any code importing `PySide6.QtCanvasPainter`), which is available only under the GPLv3 or a commercial Qt license and is not licensed to Licensee by this Agreement.

1.4 **"Modifications"** means changes Licensee makes to the Software.

1.5 **"Order Form"** means the signed schedule that states the version(s), Licensed Product(s), license type, territory, fees and term, in the form of Schedule A.

### 2. License grant

2.1 **Grant.** Subject to this Agreement and payment of the fees, Licensor grants Licensee a non-exclusive, non-transferable (except under section 12.2), non-sublicensable (except as allowed in 2.3) license, in the territory and for the term in the Order Form, to:

- (a) use, reproduce and modify the Software;
- (b) incorporate the Software and Modifications into the Licensed Product; and
- (c) distribute the Software and Modifications, in binary or source form, only as part of the Licensed Product, to end users.

2.2 **No copyleft obligation.** Licensee may distribute the Licensed Product, and keep its Modifications, under terms of Licensee's choosing, including proprietary terms, without having to release source code under the GPLv3. The GPLv3 conditions do not apply to the Software as licensed under this Agreement. This does not remove any obligation owed to a third party under a separate license (section 6).

2.3 **End users.** Licensee may sublicense the Software to end users only as embedded in the Licensed Product, on terms that are at least as protective of Licensor as sections 3, 8, 9 and 10, and that give the end user no right to extract and redistribute the Software on its own.

2.4 **Contractors.** Licensee may let contractors use the Software on Licensee's behalf, and Licensee is responsible for their compliance.

2.5 **License types.** The Order Form says which applies. If not stated, the default is **Per Product**.

- **Per Product:** one named Licensed Product (all its versions, and variants that differ only in branding or configuration).
- **Per Organization:** all products of Licensee and its majority-owned affiliates.
- **Per Device / Unit:** the number of shipped units stated in the Order Form.

### 3. Restrictions

Licensee will not, except as this Agreement allows:

- (a) distribute the Software on its own, or in a form whose main value is the Software itself (for example, a relabeled LevityDash, or a competing dashboard product with no meaningful added functionality);
- (b) offer the Software or Licensed Product as a hosted or managed service where the Software itself is what is being offered, unless the Order Form says so;
- (c) remove or change copyright, license, or attribution notices, including the third-party notices in section 6;
- (d) use Licensor's name, logo or the "LevityDash" mark to imply endorsement, or as the name of the Licensed Product, without written permission (accurate statements such as "built with LevityDash" are fine);
- (e) use the Software in violation of law, or in a way that breaks the terms of a weather data provider whose data it handles (section 6.4).

### 4. Fees and payment

4.1 Licensee will pay the fees in the Order Form: **[one-time license fee / annual fee / per-unit royalty: to be decided]**.

4.2 Invoices are due **[30]** days after the invoice date. Late amounts accrue interest at the lower of **[1]%** per month or the legal maximum. Fees are exclusive of taxes; Licensee pays applicable taxes other than taxes on Licensor's income.

4.3 Fees are non-refundable except as stated in section 8.3.

4.4 If the Order Form is per-unit or royalty based, Licensee will give Licensor a written report of units shipped within **[30]** days after each **[quarter]** and will keep accurate records for **[2]** years. Licensor may, no more than once a year and with **[30]** days' notice, have an independent party check those records during business hours, at Licensor's cost unless it finds an underpayment of more than **[5]%**.

### 5. Delivery, updates and support

5.1 Licensor will provide the Software in source form through the repository or another channel Licensor chooses.

5.2 **Updates.** Licensee may use all versions released during the term and may keep using versions released during the term after it ends, for units already distributed and for continued support of them. Versions released after the term are not licensed unless the term is renewed. **[Alternative to decide: a perpetual license for the versions available during the term.]**

5.3 **Support.** Unless the Order Form says so, Licensor has no obligation to provide support, maintenance, bug fixes or custom work. Any support level (response times, channels, hours) will be in the Order Form.

### 6. Third-party components

6.1 The Software depends on and bundles third-party components that keep their own licenses and are not relicensed by this Agreement. The current list is in `LICENSING.md`, with notices in the repository (for example `resources/data/NOTICE.md`, `resources/icons/LICENSES.md`, `resources/fonts/*/LICENSE.txt`, and the notice in `Modules/beam/__init__.py`).

6.2 **Licensee's duty.** Licensee will comply with those licenses in the Licensed Product, including keeping and shipping required notices and attribution. In particular:

- **Qt / PySide6** (LGPLv3): keep Qt dynamically linked and replaceable by the end user, and provide the LGPLv3 text and notices. A locked single-file build that prevents replacing Qt does not meet this condition.
- **Qt Canvas Painter**: do not include it unless Licensee has its own commercial Qt license that covers it.
- **Data files** such as the star catalogue (CC BY-SA 4.0): keep the attribution; the share-alike condition applies to the data file itself.
- **Fonts and icon fonts** (SIL OFL, Apache-2.0): ship the license files, and do not sell the fonts on their own.

6.3 Licensor will tell Licensee in release notes if a new dependency changes this list in a way that affects proprietary distribution, but Licensee remains responsible for its own legal review of the build it ships.

6.4 **Weather and data providers.** The Software can fetch data from third-party services (for example Open-Meteo, OpenWeatherMap, PirateWeather, WeatherFlow). Their terms of service are between Licensee (or its end users) and the provider, and some free tiers are non-commercial. Licensee is responsible for getting any API plan or key the provider requires for Licensee's use. This Agreement does not give any rights to provider data.

### 7. Ownership and contributions

7.1 Licensor keeps all rights in the Software. This Agreement transfers none to Licensee, other than the license in section 2.

7.2 Licensee owns its Modifications and the Licensed Product, subject to Licensor's rights in the underlying Software.

7.3 **Feedback.** Licensee grants Licensor a perpetual, worldwide, royalty-free license to use any feedback or suggestions Licensee gives about the Software, with no obligation to Licensee.

7.4 **Contributions back.** Licensee is not required to contribute Modifications. If it chooses to, they are accepted under the contribution terms in `LICENSING.md`.

### 8. Warranty and indemnity

8.1 **As is.** The Software is provided **"AS IS"**, without warranty of any kind, express or implied, including merchantability, fitness for a particular purpose, title and non-infringement, to the extent allowed by law.

8.2 **Authority.** Licensor represents that it has the right to grant the license in section 2 for the Software that it owns. This representation does not extend to third-party components (section 6) or to code that Licensee has modified.

8.3 **IP indemnity (optional, to decide).** **[If included:]** Licensor will defend Licensee against a third-party claim that the unmodified Software, as delivered, infringes that party's copyright in the territory, and will pay the resulting damages and costs awarded, if Licensee gives prompt notice, lets Licensor control the defense, and cooperates. If such a claim succeeds or is likely to, Licensor may modify the Software, obtain a right to continue, or end the license and refund prepaid fees for the unused term. This is Licensee's only remedy for infringement claims. This indemnity does not cover Modifications, combinations with other software, third-party components, or use outside this Agreement. **[Many small authors leave the indemnity out; this is a business decision.]**

8.4 **Indemnity by Licensee.** Licensee will defend and indemnify Licensor against third-party claims arising from the Licensed Product (other than claims covered by 8.3) or from Licensee's breach of sections 3 or 6.

### 9. Limitation of liability

9.1 To the extent allowed by law, neither party is liable to the other for indirect, incidental, special, consequential, or punitive damages, or for lost profits, revenue or data, however caused.

9.2 Licensor's total liability under this Agreement is limited to the fees Licensee paid in the **[12]** months before the claim arose.

9.3 These limits do not apply to Licensee's breach of sections 2 or 3, to payment obligations, or to liability that cannot be limited by law.

### 10. Confidentiality

Each party will keep the other's non-public information that is marked or clearly confidential (including fees, and unreleased source code a party gives the other) confidential, use it only for this Agreement, and protect it with reasonable care. This does not cover information that is public through no fault of the receiver, already known, independently developed, or lawfully received from a third party. Any copy of the Software already available under the GPLv3 is public. A party may disclose information required by law after notifying the other where legally possible.

### 11. Term and termination

11.1 **Term.** The term is stated in the Order Form: **[perpetual / one year, renewing yearly]**.

11.2 **Termination for breach.** Either party may terminate on **[30]** days' written notice if the other materially breaches and does not cure within that time. Licensor may terminate immediately if Licensee breaches section 3 and does not stop within **[10]** days of notice.

11.3 **Effect.** On expiry or termination, Licensee will stop making new copies and new shipments of the Software under this Agreement. Units already lawfully distributed to end users may continue to be used by those end users. Sections 1, 3 (as to past use), 4 (unpaid amounts), 6.2, 7, 8.1, 8.4, 9, 10, 11.3 and 12 survive.

11.4 **Fallback.** Ending this Agreement does not take away Licensee's rights under the GPLv3, which stay available to everyone for the versions Licensor has published under it, provided the GPLv3 conditions are met.

### 12. General

12.1 **Governing law and venue.** This Agreement is governed by the laws of **[jurisdiction]**, without regard to conflict-of-law rules. The courts of **[venue]** have exclusive jurisdiction, except that Licensor may seek injunctive relief anywhere to protect its intellectual property.

12.2 **Assignment.** Licensee may not assign this Agreement without Licensor's written consent, except to a successor of all or substantially all of its business that assumes it in writing and is not a competitor of Licensor. Licensor may assign it to a successor to the Software.

12.3 **Export and sanctions.** Licensee will comply with applicable export, sanctions and anti-corruption laws.

12.4 **Notices** go to the addresses in the Order Form, by email with confirmation or by courier.

12.5 **Entire agreement.** This Agreement and the Order Form are the whole agreement and replace earlier discussions. Changes must be in writing and signed by both parties. If they conflict, the Order Form controls. If a term is unenforceable, the rest stays in force. A failure to enforce is not a waiver.

12.6 **No agency or exclusivity.** The parties are independent contractors. This Agreement does not restrict Licensor from licensing the Software to others or from publishing it under the GPLv3.

12.7 **Relationship to earlier licenses.** Copies of LevityDash released under the MIT license (v0.2.0-beta.3 and earlier, PyPI 0.1.0b*) remain under that license (`LICENSE-MIT-HISTORIC.txt`) and are not affected.

---

## Schedule A: Order Form (template)

| Item | Value |
|---|---|
| Licensee | [legal name, address, contact] |
| Effective Date | [date] |
| Licensed Product(s) | [name(s) and short description] |
| License type | [Per Product / Per Organization / Per Device] |
| Units (if per device) | [number or "unlimited up to $X"] |
| Software version(s) licensed | [from vX.Y.Z; all later versions during the term] |
| Territory | [worldwide / list] |
| Term | [perpetual / 1 year auto-renew] |
| Fees | [amount, currency, payment schedule] |
| Royalty reporting | [none / quarterly] |
| Hosted use allowed (3(b)) | [no / yes: describe] |
| Support | [none / description, response times] |
| IP indemnity (8.3) | [included / not included] |
| Notices | [addresses] |

Signed for Licensor: ______________________  Date: __________

Signed for Licensee: ______________________  Date: __________

---

## Notes for the author (delete before use)

These are open decisions and checks, not part of the agreement:

1. **Who is the Licensor.** Today the copyright is held by you personally. If you form an LLC for this, assign the copyright to it first.
2. **Pricing model.** Per product, per organization, per device, or royalty. Fee and tiers are blank on purpose.
3. **Perpetual vs term (5.2, 11.1).** Decide whether customers keep rights to the versions they paid for. Perpetual-for-what-you-paid is the common small-vendor choice.
4. **Indemnity (8.3).** Optional. Easier to leave out at first; some enterprise customers will ask for it.
5. **Contributor rights.** You can only grant this license for code you own. So far every human commit is yours (see `license-audit.md`). Once outside pull requests arrive, you need a CLA or copyright assignment, otherwise their code can only go out under the GPLv3. `LICENSING.md` has a contribution paragraph that does this; have a lawyer check it.
6. **AI-generated code.** Much of the history is Claude/OpenCode co-authored. The audit's view is that this affects enforceability more than your ability to license. Worth confirming with the lawyer.
7. **Build prerequisites before a first sale.** `pysolar` is already out of `pyproject.toml` and `resources/icons/LICENSES.md` exists. What remains: keep Canvas Painter out of the commercial build, and re-run the dependency check at the time of the first sale.
8. **Governing law and venue** depend on where you want to be sued from.
9. **Trademark.** "LevityDash" is not registered as far as I know; 3(d) is a contract term, not a trademark right.
10. **Tax, invoicing, and refund policy** are outside this draft.
