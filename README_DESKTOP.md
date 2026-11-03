# FinPilot Desktop

FinPilot is a native Tkinter personal finance dashboard. It includes a savings simulator, cashflow and category charts, a searchable transaction ledger with CSV export and undo, monthly budget controls, light and dark themes, and local JSON storage.

## Start

Double-click `run_finpilot.pyw`, or run `python finpilot/main.py`. Python 3.11+ is required. No browser or npm install is needed.

The main app and data file live in `finpilot/`. The old standalone file is now a compatibility launcher. New data saves to `finpilot/finpilot_data.json`. Runtime data is excluded from version control.

## Verify

Run `python tests/verify_desktop.py` to check layouts, transactions, budget limits, charts, themes, JSON saving, and CSV export.

Windows scales the complete Tkinter interface at the display's scaling setting. Cards and forms rearrange as the window narrows; long views scroll.


## Future Planner

Open **Future planner** in the sidebar, or launch `python finpilot/main.py --view planner`.

- Month-end forecast: recorded net balance (or your actual balance snapshot), confirmed income, upcoming bills, and estimated variable spending.
- Payments & patterns: add/edit monthly or one-off income and expenses. Review recurring patterns before confirming. Matching uses category, description, type, a 10% amount tolerance (minimum Rs. 1), and seven days around the scheduled date. Each ledger transaction can satisfy one payment only.
- Savings goals: target, deadline, allocated savings, required monthly contribution, overdue/completed status, and combined funding gap. Allocations are planning records, not transfers or expenses.
- What-if studio: preview a 0–50% reduction in remaining variable spending and an additional purchase without changing the ledger. Use Left/Right or Home/End on the slider.
- Forecast sources: review already-recorded matches, scheduled amounts, and every historical estimate. Override a category’s remaining spending for the current month (zero excludes it), or clear the overrides to return to automatic estimates. Forecast ranges are scenarios, not statistical confidence intervals.

Planning data is saved separately in `finpilot/finpilot_data_planning.json`. Existing transaction JSON files remain compatible. Corrupt planning files are preserved and edits are blocked with a visible error. Goals and schedules are not cleared by the existing transaction/budget reset controls.

The estimate assumes your ledger is complete. History uses up to three complete months; a partial first month is excluded. Sparse records do not justify predictions of unknown income. Set an actual balance for a bank-balance forecast, and check payment matches when amounts or dates change.

Additional verification: `python tests/test_planning.py` and `python tests/verify_planner.py`.

## OpenRouter AI assistant

Open **AI assistant**, or run `python finpilot/main.py --view assistant`.

1. Select ALL history or a recorded month. Local report works immediately without a key or internet.
2. Open Connection settings. Enter your OpenRouter API key and an available text model ID (`provider/model`), then choose Save connection. The key and model are saved in a Windows DPAPI-encrypted sidecar bound to your Windows account; chat history stays in memory. Replace them in the same dialog, or choose Forget saved key.
3. Review the included transaction descriptions, then enable data sharing and send a question. Selected transaction dates, types, amounts, categories and IDs, locally calculated totals, and recent chat context are sent to OpenRouter and its model provider. Descriptions are included by default, as requested; uncheck the descriptions option to exclude them. Nothing is sent on startup, preview, filter changes, or entering a key.

Income, expense, net cash flow, donut segments and monthly bars are computed in Python using integer paise. AI supplies plain-text explanations only; it cannot execute code or edit your ledger. Reports show their scope and snapshot date. Net cash flow is not an account balance. The cash-flow chart shows the latest 12 recorded months while totals include the entire selection. Forecasts, goals and budgets are not included in this initial assistant release.

Requests run on a background thread, with a 45-second network timeout. Cancel discards the response locally; it cannot retract a request already sent or prevent a provider charge. Changing scope or records resets follow-up context. Requests larger than 100 KB of financial snapshot are rejected before networking; select a single month. Model context limits can be lower. API usage, availability and data handling depend on OpenRouter and the chosen provider. AI prose can contain errors even though the displayed chart totals are deterministic.

Integration follows the [OpenRouter chat-completion API](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion). No additional Python dependencies are required. Mock-response tests cover the client lifecycle; live inference depends on your key and the selected provider.

Verification: `python tests/test_assistant.py` and `python tests/verify_assistant.py` cover exact totals, privacy defaults, malformed/error responses, payload limits, cancelled responses, scope resets, minimum window size, themes and session key cleanup.

The default model is `thinkingmachines/inkling:free`. Requests enforce free-only model IDs and zero input/output price, prefer low-latency providers, and disable extended reasoning for shorter responses. Free-provider availability and limits still apply. Encrypted `*_connection.dpapi` files are excluded from Git and the source ZIP. Persistence does not extend the API key’s expiration.

Detailed evaluation includes all selected transaction IDs, dates, amounts, types, categories and descriptions, with exact category-by-month and description-level expense totals. ALL history and descriptions are selected by default. Merchant or purpose details come only from recorded notes; missing details are not inferred. The payload size guard rejects oversized selections rather than silently dropping records.

## Glass-inspired report workspace

The assistant uses a fixed composer and independent conversation/report scrolling. Wide windows show both panes; narrow windows use Conversation and Financial report tabs. Data-sharing controls collapse into a dialog on short windows. Markdown headings, emphasis, bullets and pipe tables are rendered natively. Table cells wrap; wide tables scroll horizontally; tables over 12 rows have page controls. Malformed table rows preserve extra cell text. Generated HTML/code is never executed.

Card shadows and reflected edges use cached Pillow images, regenerated after resizing settles. Install optional visual support with `python -m pip install -r requirements-desktop.txt`; without Pillow the app uses vector cards. Native DPI behaviour is unchanged, so Windows scaling may still soften text. No universal frame-rate guarantee is made.

Renderer verification: `python tests/verify_rich_report.py`. Existing desktop, planner and assistant regression scripts remain available. Local report demonstrates a category table without sending an API request.
