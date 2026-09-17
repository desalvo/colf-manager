# Changelog

## r102-full — Audit operativo e retention configurabile

- Registro audit amministrativo con ricerca per testo e intervallo di date.
- Retention automatica configurabile dalle impostazioni, default 12 mesi; 0 disabilita il purge automatico.
- Pagina Audit con 50 record per pagina, utente, azione, oggetto, IP e dettagli.
- Purge manuale per età dei record o mantenimento degli ultimi N record; il purge manuale viene a sua volta auditato.
- Riutilizzo ed estensione dell'AuditLog già esistente, senza perdita dello storico precedente.

## r101-full - robust PDF table wrapping

- report PDF: all data-table text cells are rendered as wrapping ReportLab paragraphs;
- long text and tokens without spaces are broken within the assigned column width instead of overflowing;
- party/employer-worker table uses the same robust wrapping rules;
- regression test covers a deliberately long unbroken value.

## r100-full - report PDF layout, page totals, legal/privacy notes and signatures

- Keep report section headings with their related content on the same PDF page whenever the section fits; oversized sections may flow naturally across pages.
- Footer pagination now shows `Pagina X di Y` on every page.
- Add compact final notes to every report for calculation method, applicable legal/contractual references, and personal-data confidentiality.
- Legal notes distinguish the CCNL applicable by report period; for periods from 1 November 2025 they reference the CCNL signed 28 October 2025, including art. 17 (ferie), art. 39 (tredicesima), art. 41 (TFR), plus art. 2120 c.c., Law 297/1982 and annual INPS instructions where relevant.
- Place, report date and worker signature are always present at the end of worker reports; an uploaded worker signature is inserted automatically. Employer signature remains available when requested.
- Annual payments report supports one signature block per worker represented in the report.
- Calculation/legal/privacy material is rendered as smaller note text rather than normal report-body sections.
- Fixed signature-area structure so both stored signatures and empty signature placeholders are centred through the same nested-table layout, preserving deterministic ReportLab alignment and regression compatibility.

## r99-full - archived report regeneration

- Added a graphical **Rigenera** (↻) action to each archived report, with accessible text hint and confirmation.
- Regeneration rebuilds the selected report from current data and replaces its archived PDF in place while preserving the same database record/ID.
- The replacement updates SHA-256, size, MIME metadata and physical storage atomically; the previous file is deleted only after commit.
- Added regression coverage for in-place replacement and ID preservation.

## r98-full - payments archive usability

- payment history is sortable by every data column, with period descending as the default order
- payment history is searchable across the full archive before pagination
- payment history is paginated at 15 rows per page
- payment history is open by default and persists user open/closed overrides through the shared collapsible-state cookie
- new payment is collapsed by default and persists its state through the shared collapsible-state cookie
- payment totals were vertically compacted to reduce page length
- removed duplicate euro symbols from monetary values on the Payments page

## r97-full - robust login sessions behind proxies

- Changed Flask-Login session protection default from `strong` to `basic` so legitimate reverse-proxy/Ingress client-address changes no longer invalidate the authenticated session immediately after login.
- Added `COLF_MANAGER_SESSION_PROTECTION` (`basic`, `strong`, or `none`) and documented/configured the safer `basic` default for Docker Compose and Kubernetes.
- Added regression coverage for a login followed by a request whose apparent client address changes.

## r96-full - direct calendar navigation and usage-ranked shortcuts

- Added explicit day/month/year controls to jump directly to any calendar date while preserving the selected calendar view.
- Drag-and-drop quick choices are now ranked by usage frequency, using most recent use as the tie-breaker.
- Quick permit patterns preserve their permit category when dragged onto the calendar.
- Annual payment totals keep the Italian display format (`100,00`) and expose the canonical two-decimal value (`100.00`) as machine-readable markup, fixing the existing report regression test without changing the UI format.


## r95-full - richer archived reports and persistent collapsible state

- Archived reports show the paid/liquidated amount when the report type generates payments.
- Archived report actions use compact icon controls and approval is represented graphically with accessible hints.
- Annual summary and archived reports are collapsible and closed by default.
- All collapsible application sections persist user open/closed overrides in a cookie, while retaining template defaults when unchanged.


## r94-full - default period ordering

- Payment history now defaults to period descending, with the most recent period first.
- Archived reports now default to period descending, with the most recent period first.
- Manual column sorting remains available for archived reports.

## r93-full - payment method tracking

- Added payment method to payments with Bank transfer as the default.
- Supported methods: bank transfer, card deposit, cash and other.
- Existing payments are migrated to bank transfer.
- Payment method is shown in payment forms/details, receipts and payment reports.


## r92-full - consistent two-decimal currency formatting

- Formats monetary values in Report e paghe and generated PDF reports with exactly two decimal digits.
- Uses Italian comma decimal separator consistently (for example € 10,00 and € 125,50).
- Adds regression coverage for the shared currency formatter and report rendering.

## r91-full - final Ruff formatter cleanup

- Formatted `src/colf_manager/storage.py` exactly as required by the Ruff formatter.
- No functional changes from r89.

## r89-full - formatter production gate

- Allineata `src/colf_manager/storage.py` alla formattazione richiesta da Ruff.
- Nessuna modifica funzionale rispetto a r88; preservati i 85 test applicativi verdi.

## r88-full - ore totali permessi e formattazione gate

- Corretto il riferimento mensile dei permessi in Report e paghe: `Ore totali` usa ora i permessi del mese selezionato, non del mese corrente.
- Mantenuti separati i valori annuali dei permessi e i valori del mese filtrato.
- Allineati a Ruff format la migrazione 1012 e `storage.py`.


## r87-full - archivio report ricercabile, CF e approvazione
- Archivio report: ricerca globale, ordinamento sulle colonne dati e paginazione server-side a 10 elementi.
- Tipi report mostrati con descrizioni leggibili/localizzate invece degli acronimi tecnici.
- Nomi file archiviati prefissati con il codice fiscale del lavoratore; migrazione automatica dei report esistenti.
- Stato Approvato automatico per cedolini mensili completi e interamente pagati, con override manuale approva/non approva e ripristino automatico.
- In Report e paghe, Ore totali include anche i permessi retribuiti e non retribuiti.


## r86-full - refresh archived payroll when payments change

- When a payment is created/updated for a month with an archived monthly payroll, regenerate that payroll with the current paid/pending amounts.
- Replaces the archived PDF in place while preserving the GeneratedReport id and payment source-report relationship.
- Paid -> pending, amount/period edits and payment deletion refresh affected archived payrolls too.
- Removes the obsolete archived PDF only after the database commit succeeds.
- Adds regression coverage for marking a generated salary payment as paid and for deleting a paid payment.


## r85-full - vacation attribution threshold, due highlights and payment receipts

- Defer a multi-month continuous vacation period to its ending month only when the starting month contains at most 3 contractual vacation days.
- With 4 or more vacation days in the starting month, economically attribute each vacation day to its own month while preserving day-based entitlement consumption.
- Highlight amounts due and residual amounts in the web UI and payroll reports.
- Add a professional downloadable PDF receipt for every payment marked Paid, with due amount, actual paid amount, residual and employer signature when available.
- Add regression coverage for the 3-day/4-day vacation threshold and paid-payment receipt availability.

## r84-full - vacation carry-forward visibility and legacy recalculation

- Recompute vacation remuneration from contractual weekly hours and effective rates, ignoring stale historical `paid_hours` for vacation events.
- Keep continuous vacation remuneration entirely in the month in which the period ends.
- Add explicit monthly carry-forward notes in Report e paghe and in monthly payroll PDFs.
- Show deferred vacation remuneration in earlier months and carried-in remuneration in the ending month.
- Add regression coverage for legacy 31/07-31/08 vacation data at 20 h/week and EUR 9/hour.


## r83-full - continuous vacation payroll attribution

- Continuous vacation periods spanning multiple months are economically charged in full to the month in which the vacation ends.
- Vacation entitlement/usage remains counted on the actual contractual vacation days in each month.
- Added regression coverage for 31/07/2026–31/08/2026 at 20 h/week and EUR 9/hour: July EUR 0.00, August EUR 779.94, annual EUR 779.94.
- Updated the cross-month/rate-change regression to expect the full vacation amount in the ending month, while adding a separate paid-permit regression that remains split by month and applicable rate.

## r81 - correct vacation payroll allocation across months

- Fix vacation payroll allocation: equivalent paid hours are now distributed only over contractual vacation days (Monday-Saturday excluding national holidays), never across all calendar days spanned by an absence.
- Regression coverage for 20 weekly hours at EUR 9/hour: 31 July 2026 = EUR 30.00, August 2026 = EUR 749.94, 26-day total = EUR 779.94.
- Preserve the INPS monthly-hours / 26 conversion already used to calculate the vacation daily equivalent.

## r80 - signature centering, calendar quick delete, monthly pay breakdown

- Centra visivamente le firme PDF con una sotto-tabella dedicata nel riquadro firma.
- Aggiunge cancellazione rapida direttamente dagli eventi del calendario.
- Aggiunge in Report e paghe il dettaglio del costo mensile per ordinarie, straordinarie, permessi retribuiti, malattia e ferie.
- Aggiunge l'indicatore dei giorni di ferie usati nel mese.

## r79 - Pillow signature pixel API compatibility

- Replaced deprecated Pillow `Image.getdata()` usage with `get_flattened_data()` when available.
- Kept a compatibility fallback for older Pillow releases.
- Signature transparency, cropping, scaling and centering behaviour remain unchanged.

## r78 - report permit rendering compatibility
- restored the exact “Totale annuo” label in Reports and payroll;
- aggregates legacy `medical_visit` permits into the current medical-permit category;
- exposes the legacy-compatible `report-permit-medical_visit-*` metric key so annual values render consistently for existing data and regression tests.

## r77 - report permit aggregate scope fix
- fixed annual paid/unpaid permit aggregates being passed from the wrong route scope;
- report/payroll rendering now receives the annual permit hour totals it references;
- removed the stray undefined variables from payment detail rendering;
- aligned production-gate and package metadata to r77-full.

## r76 - calendar type-specific field visibility
- fixed calendar dialog visibility by using the native HTML `hidden` state in addition to the CSS utility class;
- permit category is shown only for permit records;
- oncological sickness is shown only for sickness records;
- employer-favour treatment is shown only for permit/sickness records;
- workplace and work-only details are shown only for ordinary/overtime records;
- added regression checks for deterministic type-specific field visibility.

## r76-full - annual permit values, signature centering and searchable expense history
- report/payroll annual summary now shows paid and unpaid permit hours;
- permit section exposes current and annual values per category, including used, accrued/total and remaining amounts;
- PDF signatures are cropped to visible ink after white-background transparency conversion, then visually centred in the signature field;
- expense/reimbursement history entries are collapsed by default;
- expense history search covers the complete archive before pagination;
- expense history is server-side paginated with a maximum of 10 entries per page.

# Changelog


## r74-full - payments, expense settlement cancellation and PDF signatures

- Transparent, centered graphical signatures in PDF reports.
- Payroll expense allocations can be returned from consolidated to planned state.
- Paid totals are derived live from existing payment records; deleted payments no longer count as paid.
- Permit values expanded in Reports & Payroll.
- Annual summaries/reports include actual payments by category and total.
- New annual all-payments PDF report.

## r72-full - calendar field relevance and automatic permit hours

- Single employer-favorable-treatment control, shown only for permits and sickness.
- Type-specific editor hides all non-pertinent properties, including paid choice for vacation.
- Permit hours are always derived from start/end time; manual `paid_hours` input is removed and legacy values are ignored by the API.
- Editing keeps the stored paid/favorable-treatment state and all applicable event properties.


## r71-full - calendar type-specific editor

- The calendar editor now exposes a single shared **Retribuita** choice for all event types.
- Ordinary/overtime, permit, sickness and vacation fields are isolated into mutually exclusive detail panels.
- New records default to paid; editing preserves the stored paid state and all type-specific values.
- Regression coverage verifies a single paid control and prevents `syncEntryKind()` from overwriting persisted paid state.

## r70-full - visible permit indicators

- Reworked the dashboard permit section into responsive per-category indicator cards so used, accrued, annual total and remaining values are always visible without horizontal scrolling.
- Added explicit paid/unpaid monthly and yearly values plus employer-favour amounts for every permit category.
- Kept shared Art. 19 pool residuals explicit and documented as common-pool balances.
- Added stable `data-metric` hooks and a regression test covering paid use, unpaid use, annual entitlement and remaining balance.

## r69-full - legacy schema bootstrap repair

- Fixed the startup compatibility shim so missing `work_entry.entry_kind`, `paid`, and `rate_override` columns are actually created and committed on existing databases.
- Added the `ix_work_entry_entry_kind` compatibility index and refreshed schema inspection before absence upgrades.
- Normalized legacy `health` absence rows to day-based `sickness` during startup compatibility repair.
- Added a regression test that boots against a legacy `work_entry` table and verifies automatic schema repair.
- Bundled the Alembic `migrations/` directory inside the Docker runtime image for operational database commands.

## r67 - dashboard label and formatter cleanup

- Restored the exact dashboard label `Tredicesima annua maturata finora` required by regression tests.
- Normalized permit/sickness rule files and migration 1010 for the production formatter.
- No functional change to the r64 sickness/permit model.

## r64 - test and formatter cleanup

- Restored the exact dashboard label `Tredicesima maturata nel mese`.
- Aligned the sickness/permit regression test with day-based sickness and categorized permits.
- Kept legacy sickness clock fields harmless: they are ignored for day-based sickness records.
- Avoided treating an unconfigured weekly schedule as a zero paid-permit entitlement.
- Applied Ruff-compatible formatting to permit/sickness rules, permit tests and migration 1010.

## r63 - production-gate regression fixes

- restored the selected dashboard period label (MM/YYYY);
- restored `Ore ordinarie` / `Ore straordinarie` labels in calendar subscription ICS summaries;
- fixed the sickness API test variable rename left from the former `health` terminology;
- no functional rollback of r62 sickness-day or employer-favour rules.

## r62 - sickness days, employer-favour overrides and visual indicators

- Restored the Italian label `Malattia` and migrated stored `health` absence records to `sickness`.
- Sickness is recorded and reported only in calendar days, with no clock-time UI.
- Added effective-dated sickness rules (2013, 2020 and 2025 renewals) with seniority-based 10/45/180-day job protection and 8/10/15 paid-day ceilings.
- Applied 50% pay through the third consecutive sickness day and 100% from the fourth day.
- Added documented-oncological-illness flag for the 50% increase in job-protection days.
- Added employer-favour override for paid sickness and permit time beyond contractual ceilings, tracked separately from the legal residual.
- Reworked overview indicators with reusable icons and safe/warning/danger states for values with limits.
- Updated payroll, annual and trend reports with sickness-day and permit-over-limit details.
- Added migration `1011_sickness_days_and_employer_override`.

## r61 - legally categorized permits and live-in rules

- Added live-in and art. 14(2) reduced-schedule flags to the worker profile.
- Added legally relevant paid/unpaid permit categories and `Other` for unpaid leave.
- Added effective-dated CCNL rules, shared art. 19 bank, training seniority rules, union and event-based limits.
- Added monthly/yearly permit usage and balances to collapsible overview sections and relevant reports.
- Added migration 1010_permit_categories_live_in.

## r54-full - 2026-09-15

- Added tokenized, revocable read-only calendar subscriptions for each worker and employer in ICS and CalDAV formats.
- Added External Application URL setting used when publishing calendar subscription links.
- Moved the regular password-change workflow into Settings and exposed Settings to authenticated users while keeping administrative sections admin-only.
- Added tests for external subscription URLs, ICS event content, and password changes from Settings.
- Retained required Compose secrets; validation scripts continue to inject validation-only values instead of introducing insecure defaults.

## r47-full - 2026-09-14

- Dashboard: added monthly thirteenth accrual, year-to-date thirteenth accrual, year-to-date TFR accrual, vacation days used in the selected month, and projected vacation days remaining in the year.
- Dashboard annual indicators now use the selected month end as cutoff while preserving existing monthly statistics.

# Changelog

## 1.0.0 - 2026-09-13

- Hardened overlay r3: self-normalizing local checks, validation test coverage, and environment-independent Docker Compose validation.

- Initial production release: worker registry, effective-dated rates, work calendar and drag/drop, absence and expense tracking, documents, payroll support PDF, TFR estimate, Docker/Kubernetes, bilingual documentation and release controls.
- Production hardening: CSRF, secure session defaults, login rate limiting, mandatory non-placeholder secrets, forced initial password change, admin user creation and audit logging.
- Corrected expense direction semantics and paid-absence allocation across month/rate boundaries; added validation and unique effective-date protection for rates.
- Hardened uploads with extension/MIME/signature checks, SHA-256 and file size metadata.
- Added Flask-Migrate/Alembic baseline, broader test coverage with an 85% gate, TLS/backup/network-policy Kubernetes improvements and configurable runtime hardening.

### Verification tooling fix (overlay r6)
- Require Twine 7.x because Hatchling may emit Core Metadata 2.5; Twine 6.x rejects metadata 2.5.
- Production gate now fails early with the installed Twine version before validating distributions.

- r6: Flask-Limiter 4.1.1+ resolves Rich/Twine 7 dependency conflict; clean-venv verification flow.

## r13-full - 2026-09-14

- Full self-contained repository package (no incremental overlay dependency).
- Split Kubernetes application and database workloads.
- Split application and database Secrets.
- Split application PVC from PostgreSQL/backup PVCs.
- Independent workload and storage deletion scripts.
- Updated kubeconform CI validation for split manifests.
- Production gate evidence updated to r13-full.

## r14-full - 2026-09-14

- Fixed concurrent database bootstrap under multi-worker Gunicorn.
- PostgreSQL schema/bootstrap is serialized with an application-specific advisory lock.
- `create_all`, legacy compatibility updates and initial admin creation now run inside the serialized bootstrap section.
- Prevents concurrent `CREATE TABLE "user"` and `pg_type_typname_nsp_index` duplicate-key failures on fresh Docker/Podman/Kubernetes starts.
- Full self-contained repository package.


## r15-full - 2026-09-14

- Fix PostgreSQL bootstrap visibility after schema creation.
- Commit transactional DDL created on the advisory-lock connection before compatibility checks and ORM queries.
- Keep the session-level PostgreSQL advisory lock held across the full bootstrap sequence.
- Prevent fresh Docker/Podman deployments from failing with `relation "user" does not exist`.

## r16-full - 2026-09-14

- Complete CRUD for workers and household employers, including optional address, phone and e-mail.
- Safe permanent deletion workflows.
- Worker-to-employer association.
- Correct previous/next month calendar controls and direct return to dashboard.
- Automatic accrued/projected vacation entitlement with optional advance use through year end.
- Automatic vacation paid-hours estimate for hourly workers.
- Estimated thirteenth-month and TFR accrual integrated in monthly/annual calculations.
- Professional PDF reports: monthly payroll, annual payroll, courtesy CU/income certification, annual TFR, hours/pay trend.
- Year-aware legal rule notes and official-source disclaimers.
- Alembic revision 1001 for employer and vacation-policy schema changes.
## r17-full - 2026-09-14

- Cedolino PDF specifico della tredicesima.
- Prospetto PDF cumulativo tredicesima + TFR con descrizione delle formule e del periodo.
- Numero contratto di lavoro e tipo contratto nell'anagrafica del lavoratore.
- Opzione contrattuale per porre economicamente a carico del datore anche le quote del lavoratore.
- Stima contributi INPS nei report quando posizione INPS e numero contratto sono presenti.
- Separazione tra contributi INPS e stima IRPEF: il datore domestico privato non viene trattato come sostituto d'imposta.
- Tabelle contributive 2025/2026 e indicazione della fonte/anno nei prospetti.
- Migration Alembic 1002_contract_tax_reporting.

## r19-full - 2026-09-14

- Fixed Ruff E701/E702/E741/F401/F841 failures introduced by the reporting work.
- Restored formatter-clean manual generator.
- Made monthly payroll PDF backward compatible when a summary lacks `thirteenth_accrual`.
- Updated PDF regression test to include the thirteenth accrual field.
- Updated production/local gate markers to r18.

## r19-full - 2026-09-14

- Added complete location management (create, view, edit, delete).
- Calendar now selects from registered locations.
- Historical work entries keep a location snapshot after location edits/deletion.
- Added database migration 1003_locations and regression tests.

## r20-full - 2026-09-14

- Unified worker terminology throughout the application and documentation.
- Added author, version and build to the application sidebar.
- Persist generated PDF reports and allow manual download/deletion.
- Added manual document deletion.
- Added full database/document/report ZIP export and destructive confirmed import.
- Added automatic orphan-file garbage collection for Docker/Podman and Kubernetes.
- Added selectable dashboard month/year and retroactive calendar entry defaults.

## r21-full - 2026-09-14

- Added regression tests for complete export/import and orphan-file maintenance.
- Restored production coverage above the configured 65% threshold without lowering it.
- Removed Bandit B608 by replacing dynamic PostgreSQL sequence SQL with bound queries and SQLAlchemy expressions.
- Production and local quality gates are now non-mutating (`ruff check` + `ruff format --check`).
- Compose validation continues to inject validation-only secrets without weakening production secret requirements.

## r23-full - 2026-09-14

- Formatted Alembic migrations `1003_locations.py` and `1004_generated_reports.py` to pass `ruff format --check`.
- Formatted `backup.py` and `storage.py` to pass `ruff format --check`.
- No functional behavior change from r21.
- Build and verification markers updated to r23-full.


## r24-full - 2026-09-14

- Fix Kubernetes PostgreSQL startup on restricted security contexts.
- Run `postgres:17-alpine` explicitly as UID/GID 70 and set `fsGroup: 70`.
- Add `fsGroupChangePolicy: OnRootMismatch` for the PostgreSQL PVC.
- Mount `/var/run/postgresql` from an `emptyDir` so the non-root process can create its Unix socket.
- Keep `allowPrivilegeEscalation: false` and drop all Linux capabilities.
- No PostgreSQL PVC deletion is required for this permission-only fix.

## r25-full - 2026-09-14

- Upgrade the bundled PostgreSQL runtime from 17 to the latest stable PostgreSQL 18.6 release.
- Pin database and backup images to `postgres:18.6-alpine`.
- Adopt the PostgreSQL 18 official-image storage layout by mounting the persistent volume at `/var/lib/postgresql`.
- Keep the Alpine `postgres` UID/GID 70 security context for the database and backup workloads.
- Add explicit PostgreSQL 17 → 18 major-upgrade guidance for existing Docker/Podman and Kubernetes installations.

## r27-full - 2026-09-14

- Pin the application image user/group to UID/GID 10001 and declare `USER 10001:10001`.
- Set Kubernetes application and maintenance workloads to explicit numeric `runAsUser`/`runAsGroup` 10001.
- Set `fsGroup: 10001` with `fsGroupChangePolicy: OnRootMismatch` for the shared application data PVC.
- Fix kubelet startup rejection when `runAsNonRoot` is enabled and the image declares the named `colf-manager` user.
- Mount ephemeral `/tmp` volumes for application and maintenance workloads while keeping `readOnlyRootFilesystem: true`.

## r28-full - 2026-09-14

- Fix mobile navigation placement and make the hamburger consistently available in the top-left sticky header.
- Scope the application drawer CSS to `.app-sidebar` so the calendar `.side-card` is no longer treated as the global navigation sidebar.
- Add a full-screen mobile scrim that closes the drawer when tapping outside it.
- Close the mobile drawer when selecting a navigation link or pressing Escape.
- Keep desktop navigation behavior unchanged and improve mobile accessibility with `aria-controls` and `aria-expanded`.

## r47-full - 2026-09-14

- Ridisegnata la navigazione: sidebar sempre disponibile, minimizzabile su desktop e drawer accessibile su mobile.
- Nuovo calendario time-grid con blocchi proporzionali alla durata, colori contestuali, modifica/cancellazione e drag-and-drop degli inserimenti recenti.
- Aggiunta pagina Impostazioni con limite degli inserimenti rapidi, configurazione SMTP/SMTPS e metodo di autenticazione disponibile.
- Aggiunto invio via e-mail di notifiche, documenti e report archiviati.
- CRUD completo per tariffe orarie e spese/rimborsi.
- Dettaglio delle spese nei report del periodo di competenza.
- Migliorata la presentazione professionale delle azioni su luoghi, datori, documenti e report.
- Aggiunte immagini fotografiche contestuali alle diverse aree dell'interfaccia e ridisegnata la testata utente.

## r55-full
- Report PDF con logo applicativo, versione/build e autore su ogni pagina.
- Firme grafiche opzionali per lavoratore e datore, caricate dalle anagrafiche (PNG/JPEG/TIFF/WEBP/BMP) e apposte ai report quando richieste.
- Archivio report con visualizzazione inline e ritorno automatico alla lista dopo la generazione.
- Registro pagamenti completo: retribuzione, contributi INPS, tredicesima, TFR, rimborsi e altre liquidazioni; stato, data, periodo, note e allegati.
- Generazione report mensile con voce automatica residua “da pagare” e contributi INPS stimati quando è presente la posizione INPS.
- Report con evidenza di quote già liquidate e residui.
- Full export/import esteso a firme, pagamenti e relativi allegati.

## r56-full - 2026-09-15
- Aggiunte compensazioni manuali multiple e parziali per ogni spesa/anticipo, in entrambe le direzioni datore↔lavoratore.
- Supportate compensazioni in contanti, bonifico, carta, altro metodo elettronico o altro metodo, con note e documento facoltativo.
- Il documento non è obbligatorio: una compensazione in contanti può essere tracciata come solo record auditabile.
- Il cedolino considera esclusivamente il saldo residuo della spesa dopo le compensazioni manuali registrate entro la fine del mese di competenza.
- Bloccata la sovracompensazione e impedita la riduzione dell'importo originario sotto le compensazioni già registrate.
- Aggiunti dettaglio della partita, storico compensazioni, modifica/eliminazione, download allegati e audit dedicato.
- Compatibilità preservata per i vecchi record `reimbursed`: continuano a risultare integralmente regolati.
- Nuova migrazione Alembic `1007_expense_settlements`.
- Report PDF aggiornati con importo originario, compensato e residuo, oltre al dettaglio delle compensazioni manuali.

## r59 - Ruff formatter cleanup

- Normalized migrations 1006 and 1007 to the `ruff format` style used by the production gate (`line-length = 100`).
- No functional or database-schema changes relative to r58.
- Updated package/build labels and verification scripts to r59-full.

## r58 - production gate formatting cleanup

- Reformatted Alembic migrations 1006, 1007 and 1008 to match Black output.
- No functional changes to the r57 expense settlement, carry-forward or installment logic.
- Updated package/build labels and verification scripts to r58-full.

## r57 - carry-forward and installment recovery

- Added carry-forward of expense/reimbursement residuals to a later month.
- Added installment plans by installment count or fixed installment amount, with final remainder handling.
- Later manual settlements reduce future still-open quotas while preserving earlier consolidated payroll quotas.
- Monthly payroll generation locks the quota actually included in that payroll to prevent duplicate reimbursement.
- Added `1008_expense_recovery_allocations` migration and full-export support for recovery plans and settlement evidence.
- Fixed missing `Decimal` import in `reporting.py` that caused Ruff F821 errors and payroll PDF test failure.
- Formatter-cleaned expense settlement migrations.


## r60 - hour type model
- Renamed paid work hours to ordinary hours with a paid/unpaid flag (paid by default).
- Added overtime hours with a paid/unpaid flag and optional per-entry hourly-rate override.
- r60 temporarily renamed sickness to health and made health entries paid by default; r62 restores the sickness label.
- Added permit hours, paid by default with optional unpaid state.
- Vacation remains a day-based entitlement and is exposed only in days.
- Added migration 1009 and updated calendar, summaries, payroll reports and tests.

## r68-full
- Fixed production gate version/build validation: application version is checked against __version__, build revision against __build__.
- Added explicit diagnostics for future version/build mismatches.
