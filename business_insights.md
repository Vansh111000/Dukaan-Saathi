# Dukaan Saathi — Features 6, 7 and 8
## Implementation Plan, Architecture and Logic

**Date:** 31 October 2026  
**Project:** Dukaan Saathi  
**Backend:** FastAPI  
**Database:** SQLite  
**Shopkeeper interface:** Telegram Bot  
**Customer reminders:** Exotel SMS  
**AI services:** Sarvam AI, Google Cloud Vision and Gemini

---

# Feature 6 — Dynamic Daily Business Summary

## 1. What we are implementing

The original feature was an evening summary containing:
- Daily digital sales.
- Who owes the shopkeeper money.
- Items that are due for restocking.
- A natural-language summary in Hinglish.

We are implementing this as a **Dynamic Daily Business Summary** rather than generating it only in the evening.

A business-day session starts at **12:00 AM and runs until 11:59 PM** in the shop's local timezone. It is updated throughout the day whenever a relevant transaction is recorded. At midnight, the previous day is retained for history and the next day's summary begins.

The summary should show:

1. Total sales recorded today.
2. Digital/UPI sales.
3. Cash sales, if recorded.
4. New udhar recorded today.
5. Payments and udhar repayments received today.
6. Customer-wise outstanding udhar.
7. Total outstanding udhar across customers.
8. Items that are low on stock or due for restocking.

The bot should present the figures in simple Hinglish. The underlying amounts and calculations must be computed by the backend, not invented by an LLM.

## 2. How we are implementing it

### Input channels

The shopkeeper interacts with the Telegram Bot using text, voice notes and images.

- **Sales:** Record the sale amount and payment mode. For item-level stock and profit calculations, item name, quantity and selling price must be recorded separately.
- **Udhar:** Record only customer name, phone number and udhar amount. We do not need to ask which items the customer took as part of the udhar entry.
- **Repayment:** Record the customer and amount repaid.
- **Purchases:** Supplier bill images are processed separately and update purchase and inventory records.
- **Restocking status:** Read from the inventory and restocking modules.

### Voice and text processing

For voice notes:

1. Telegram receives the audio.
2. The backend downloads the audio.
3. Sarvam AI transcribes the voice note.
4. Gemini extracts the required fields into structured data.
5. The backend validates the extracted values.
6. The bot asks the shopkeeper to confirm uncertain or consequential entries.
7. The confirmed transaction is saved to SQLite.

For typed messages, the text can go directly to Gemini for structured extraction, followed by the same validation and confirmation process.

### Example udhar input

Shopkeeper:

> "Ramesh ka 500 rupaye udhar likh do. Number 9876543210."

Extracted fields:

```json
{
  "customer_name": "Ramesh",
  "phone_number": "9876543210",
  "amount": 500,
  "transaction_type": "UDHAR"
}
```

No item details are required for this udhar entry.

## 3. Database design

The following SQLite tables support this feature.

### `sales`

Stores sale-level information such as shop, date, total amount and payment status.

### `sale_items`

Stores item-level quantities and selling prices when the shopkeeper records itemised sales. This is needed for inventory and item-level profit; it is not required just to record an udhar balance.

### `payments`

Stores payment collections and payment mode, such as UPI or cash. Keep payment collection records distinct from sales so that repayment of old udhar is not counted as a new sale.

### `customers`

Stores one customer account per shop and phone number.

Suggested fields:

| Field | Purpose |
|---|---|
| `id` | Internal customer ID |
| `shop_id` | Shop that owns this customer ledger |
| `customer_name` | Customer name |
| `phone_number` | Normalised phone number |
| `outstanding_balance` | Current outstanding udhar |
| `created_at` | Record creation time |
| `updated_at` | Last update time |

Use a unique constraint on:

`(shop_id, normalized_phone_number)`

The customer's name is a display field, not part of the identity key. The same customer may have separate accounts at different shops.

### `udhar_transactions`

Stores every new udhar entry and repayment.

| Field | Purpose |
|---|---|
| `id` | Transaction ID |
| `customer_id` | Customer account |
| `shop_id` | Shop |
| `transaction_type` | `UDHAR` or `REPAYMENT` |
| `amount` | Amount of the transaction |
| `transaction_date` | Date and time |
| `due_date` | Optional due date |

### `inventory`

Stores the current stock quantity for each product at each shop. The summary reads this table or the restocking recommendations to show low-stock items.

## 4. Implementation logic

### A. Dynamic summary refresh

Whenever a transaction is successfully saved:

1. Identify the shop and its local business date.
2. Read that day's sales and payment records.
3. Calculate sales totals by payment mode.
4. Read udhar entries and repayments recorded that day.
5. Read each customer's current outstanding balance.
6. Read low-stock and due-for-restock items.
7. Build a structured summary object.
8. Ask Gemini to turn the already-calculated figures into a short Hinglish message.
9. Send the updated summary through Telegram.

The backend should calculate all financial totals using SQL/Python. Gemini should only phrase the result; it must not calculate or guess the figures.

### B. Udhar balance logic

Each customer has a running outstanding balance.

- New udhar: increase the balance.
- Repayment: decrease the balance.
- The ledger records every change.
- The customer balance is updated in the same database transaction as the ledger entry.

Example:

| Event | Amount | Outstanding |
|---|---:|---:|
| First udhar | +₹500 | ₹500 |
| Additional udhar | +₹300 | ₹800 |
| Repayment | -₹400 | ₹400 |

The ledger is the source of truth. The stored balance is a convenient current value and should be reconcilable from the ledger.

### C. Summary calculations

Keep these concepts separate:

- **Today's sales:** value of sales made today, including credit sales.
- **Today's collections:** money actually received today.
- **New udhar today:** credit newly given today.
- **Udhar repayment today:** money collected against previous credit.
- **Total outstanding udhar:** sum of all customers' current balances.

A repayment of old udhar increases today's collections and reduces outstanding udhar. It does not create a new sale.

### D. Hinglish response generation

The backend sends Gemini a structured object, for example:

```json
{
  "business_date": "2026-10-31",
  "total_sales": 12500,
  "upi_sales": 7500,
  "cash_sales": 3000,
  "new_udhar": 2000,
  "collections_today": 10500,
  "total_outstanding_udhar": 18500,
  "customers_with_outstanding": [
    {"name": "Ramesh", "outstanding": 500},
    {"name": "Suresh", "outstanding": 1200}
  ],
  "restock_items": ["Cooking oil", "Rice"]
}
```

Gemini generates a concise Hinglish summary using only these supplied values. Customer details should only be shown to the shopkeeper who is authorised to view that shop's records.

### E. Daily session handling

- Use the shop's local timezone to assign the business date.
- For the initial India PoC, use `Asia/Kolkata`.
- Store timestamps consistently, preferably in UTC.
- Convert timestamps to the shop timezone for daily reports.
- At midnight, the new business date becomes active.
- Historical summaries can be reconstructed from transaction records.

Do not rely on a single midnight job to calculate the day's totals. The summary should refresh after transactions and can also be reconciled periodically.

## 5. Customer SMS reminders using Exotel

The shopkeeper uses Telegram. Customers receive reminders through Exotel SMS; they do not need Telegram.

Reminder flow:

1. Find customers with outstanding balances.
2. Check whether a reminder is due and permitted.
3. Check reminder history to prevent duplicate messages.
4. Submit the approved SMS template through Exotel.
5. Store the provider message ID and submission status.
6. Update delivery status using Exotel callbacks/webhooks where available.
7. Stop or adjust reminders when the balance is cleared.

Illustrative SMS:

> Namaste Ramesh ji, aapka Sharma General Store mein ₹500 ka payment pending hai. Kripya apni suvidha ke anusaar payment kar dein. Dhanyavaad!

Before production use, confirm Exotel account setup, applicable DLT registration, sender header, template approval, message classification and consent requirements. The exact regulatory classification must be verified with Exotel; do not assume it.

Suggested table: `sms_notifications`, containing customer ID, message type, amount at send time, provider message ID, sent time and delivery status.

---

# Feature 7 — Restock Advice

## 1. What we are implementing

The restocking feature recommends:

- **What** products the shop should purchase.
- **When** the shop should purchase them.
- **How much** it may need to purchase.
- Whether local purchasing activity for the product is increasing.
- Whether local purchase prices appear favourable.

The recommendation is based on four main sources:

1. The shop's own buying and selling history.
2. Current stock and supplier lead time.
3. Local Market Intelligence, which aggregates purchasing activity and price information from nearby participating shops.
4. Additional context such as festivals and weather, where relevant data is available.

The key design decision is that **Local Market Intelligence feeds directly into the restocking engine**. It is not only a separate notification feature.

## 2. How we are implementing it

### A. Shop-level sales and inventory data

The system needs:

- Product name and standard product ID.
- Units sold over time.
- Current stock.
- Purchase quantities.
- Purchase price.
- Supplier lead time.
- Stock adjustments such as damaged or expired goods.

The shop's own sales history gives the baseline demand for each product.

### B. Local Market Intelligence input

Local Market Intelligence processes supplier bills uploaded by participating shops.

Pipeline:

1. Shop uploads a supplier bill through Telegram.
2. Google Cloud Vision extracts the text.
3. Gemini converts the OCR text into structured bill fields.
4. Product names, brands, pack sizes and units are normalised.
5. Validated purchase items are saved in SQLite.
6. Eligible records are aggregated by product, locality and time period.
7. The system calculates local purchasing trends and local price statistics.
8. The restocking engine retrieves the relevant product's aggregate statistics.

The local signal is a **proxy for demand**, because it reflects purchasing activity by nearby shops. It is not direct proof of consumer sales. The engine must not automatically translate a neighbourhood purchasing increase into the same percentage increase in an individual shop's sales.

### C. Festivals and seasonal events

Use a festival/calendar dataset to identify upcoming events relevant to the shop's location and product category.

Implementation logic:

1. Identify an upcoming festival or seasonal event.
2. Identify products that may be relevant to it.
3. If the shop has historical sales from similar periods, compare those periods with normal demand.
4. Use the shop's own historical pattern as the stronger signal.
5. If there is no relevant history, show a cautious seasonal suggestion rather than claiming a reliable forecast.

### D. Weather

Use a weather API to retrieve forecasts for the shop's area.

Implementation logic:

1. Retrieve the forecast for the relevant period.
2. Identify product categories for which weather may plausibly affect demand.
3. Use weather only as a supporting signal.
4. Do not change demand forecasts for unrelated products.
5. If the relationship has not been established from data, present weather as context rather than a numerical demand adjustment.

### E. Local price trends

Use the Local Price Index to compare the shop's latest purchase price with the aggregated local median/range for an equivalent product.

The system can advise the shopkeeper when the recorded purchase price is higher or lower than the local comparison. Comparisons must account for equivalent brand, variant, pack size, unit, taxes and discounts where those details are available.

## 3. Core restocking calculations

### A. Stock calculation

`Closing stock = Opening stock + Purchases - Units sold - Other stock reductions`

Other stock reductions include damaged, expired, missing or manually adjusted stock. Returns must be recorded with the correct direction.

### B. Average daily sales

`Average daily demand = Units sold during the selected period / Number of days in that period`

Example:

- 84 litres of oil sold over 7 days.
- Average daily demand = 84 / 7 = 12 litres per day.

### C. Estimated days remaining

`Days remaining = Current stock / Adjusted average daily demand`

Example:

- Current stock = 36 litres.
- Average daily demand = 12 litres.
- Estimated stock remaining = 3 days.

### D. Reorder point

`Reorder point = (Average daily demand × Supplier lead time) + Safety stock`

Example:

- Average daily demand = 12 litres.
- Supplier lead time = 2 days.
- Safety stock = 12 litres.
- Reorder point = (12 × 2) + 12 = 36 litres.

If current stock is at or below 36 litres, recommend placing an order.

## 4. How Local Market Intelligence changes the recommendation

The engine should retain two demand values:

- Baseline demand from the shop's own sales.
- Adjusted demand after considering the local market signal.

Example:

| Input | Value |
|---|---:|
| Shop's average daily oil sales | 8 litres |
| Current stock | 24 litres |
| Supplier lead time | 2 days |
| Local purchasing activity | Increasing |

The shop's own sales indicate approximately three days of stock. If nearby shops are also increasing their purchases of oil, the system can recommend restocking earlier or considering a larger order.

For the first implementation, use a conservative, configurable adjustment to the shop-level forecast. Do not simply increase the shop's forecast by the exact neighbourhood percentage. Tune the adjustment using historical forecast performance as data becomes available.

## 5. Example restocking recommendation

> **Cooking Oil — Restock Recommended**
>
> - Current stock: 24 litres
> - Average daily sales: 8 litres
> - Estimated stock remaining: 3 days
> - Supplier lead time: 2 days
> - Local purchasing activity: Increasing
> - Recommendation: Consider placing an order now to avoid running low.
>
> Local purchasing activity is an additional signal; actual sales at your shop may differ.

## 6. SQLite data required

| Table | Purpose |
|---|---|
| `products` | Standard product catalogue |
| `shop_products` | Products sold by each shop |
| `sales` / `sale_items` | Shop-level sales history |
| `purchase_bills` | Supplier bill metadata |
| `purchase_items` | Product, quantity, unit and purchase price |
| `inventory` | Current stock by shop and product |
| `stock_movements` | Purchases, sales, damage, returns and adjustments |
| `area_product_weekly_stats` | Aggregated neighbourhood purchasing activity |
| `price_indices` | Local median and price range |
| `restock_recommendations` | Generated recommendations |

## 7. Privacy and reliability rules

- Local Market Intelligence participation should be opt-in.
- Use a minimum independent-shop threshold before displaying an aggregate. A starting threshold of five shops can be tested.
- Do not disclose individual shop identities, exact quantities or supplier details.
- Deduplicate uploaded bills.
- Do not include customer names or phone numbers in market analytics.
- Clearly label the locality and time period of local statistics.
- If there is insufficient local data, fall back to shop-level restocking logic and say that local data is unavailable.
- Treat local purchasing activity as an indicator, not confirmed consumer demand.

---

# Feature 8 — Item-Level Profit

## 1. What we are implementing

The initial idea was a monthly approximate profit estimate based on sales minus purchases. We have since simplified the scope.

For the current PoC, Feature 8 will calculate **item-level gross profit**, rather than full monthly net profit or accounting profit.

The system will show:

- Profit earned per unit of an item.
- Total profit for the quantity sold.
- Optionally, a comparison of profit across products.

It will not calculate rent, salaries, utilities or other operating expenses.

## 2. Calculation logic

### A. Profit per unit

`Profit per unit = Selling price per unit - Purchase price per unit`

### B. Total profit for an item

`Total item profit = Profit per unit × Units sold`

### Example

A shop purchases cooking oil at ₹120 per litre and sells it at ₹150 per litre.

| Metric | Value |
|---|---:|
| Purchase price per litre | ₹120 |
| Selling price per litre | ₹150 |
| Profit per litre | ₹30 |
| Quantity sold | 20 litres |
| Total item profit | ₹600 |

Calculation:

`₹150 - ₹120 = ₹30 profit per litre`

`₹30 × 20 = ₹600 total item profit`

## 3. How we are implementing it

1. Supplier bills provide purchase prices and quantities.
2. OCR extracts bill text using Google Cloud Vision.
3. Gemini structures the extracted information.
4. The shopkeeper confirms uncertain product, quantity and price fields.
5. The purchase item is saved in SQLite and associated with a standard product.
6. Itemised sales record the product, quantity sold and selling price.
7. The profit service retrieves the relevant purchase cost and selling price.
8. It calculates per-unit and total item profit.
9. The result is shown through Telegram.

## 4. Purchase price selection

A product may be purchased at different prices over time. The PoC must use a consistent cost method.

For the initial implementation, use a simple **weighted average purchase cost** for each shop and product:

`Weighted average cost = Total purchase value of available units / Total purchased units`

Example:

| Purchase | Quantity | Unit cost | Total cost |
|---|---:|---:|---:|
| First purchase | 10 units | ₹100 | ₹1,000 |
| Second purchase | 20 units | ₹110 | ₹2,200 |
| Total | 30 units | | ₹3,200 |

`Weighted average cost = ₹3,200 / 30 = ₹106.67 per unit`

If the shop's current cost information is missing or the product cannot be matched confidently, do not invent a profit figure. Mark the profit as unavailable until the purchase cost is confirmed.

## 5. SQLite data required

| Table | Purpose |
|---|---|
| `products` | Standard product identity |
| `purchase_items` | Purchase quantity and unit cost |
| `sale_items` | Quantity sold and selling price |
| `item_profit_results` (optional) | Cached calculated results, if needed |

Profit can also be calculated from the purchase and sales records using SQL/Python without storing a separate result table.

## 6. Important distinction

This is **item-level gross profit**, not net business profit.

It does not subtract:
- Shop rent.
- Employee salaries.
- Electricity and utilities.
- Delivery costs.
- Other operating expenses.

The result is only as reliable as the purchase prices and itemised sales quantities entered into the system.

Udhar entries do not need item details. However, if a shop wants item-level profit, it must record itemised sales separately, regardless of whether the customer pays by UPI, cash or credit.

---

# Shared Implementation Architecture

## 1. End-to-end flow

```text
                    SHOPKEEPER
                         |
                    Telegram Bot
                         |
                      FastAPI
                         |
        +----------------+----------------+
        |                |                |
   Voice Input       Image Input       Text Input
        |                |                |
    Sarvam AI       Google Vision       Gemini
        |                |                |
        +----------------+----------------+
                         |
              Gemini Structured Extraction
                         |
               Validation and Confirmation
                         |
                      SQLite
                         |
        +----------------+----------------+
        |                |                |
 Dynamic Summary   Restocking Engine   Item Profit
        |                |                |
        +----------------+----------------+
                         |
                  Telegram Response

Customer Udhar Ledger
        |
Reminder Scheduler
        |
   Exotel SMS API
        |
 Customer's Phone
```

## 2. Suggested backend modules

```text
app/
├── main.py
├── database/
│   ├── connection.py
│   ├── models.py
│   └── migrations/
├── routers/
│   ├── telegram.py
│   ├── sales.py
│   ├── udhar.py
│   ├── purchases.py
│   ├── inventory.py
│   ├── summary.py
│   ├── restocking.py
│   └── notifications.py
├── services/
│   ├── sarvam_stt.py
│   ├── vision_ocr.py
│   ├── gemini_extractor.py
│   ├── transaction_validator.py
│   ├── udhar_service.py
│   ├── summary_service.py
│   ├── exotel_sms.py
│   ├── inventory_service.py
│   ├── local_market_intelligence.py
│   ├── restocking_service.py
│   └── item_profit_service.py
└── jobs/
    ├── reminder_job.py
    ├── daily_reconciliation_job.py
    └── weekly_market_intelligence_job.py
```

## 3. Implementation order

1. **SQLite and transaction foundation:** shops, products, sales, payments, customers and udhar ledger.
2. **Telegram interaction:** text/voice input, parsing, validation and confirmation.
3. **Dynamic daily summary:** calculate sales, collections, outstanding udhar and stock warnings.
4. **Exotel SMS:** reminder scheduling, message submission and delivery tracking.
5. **Supplier bill processing:** Vision OCR, Gemini extraction, validation and purchase records.
6. **Inventory:** stock movements, current stock and supplier lead times.
7. **Local Market Intelligence:** product normalisation, local price index and neighbourhood purchasing trends.
8. **Restocking engine:** combine shop-level demand with local market signals, supplier lead time, festivals and relevant weather context.
9. **Item-level profit:** calculate unit and total profit from purchase cost and itemised sales.
10. **Testing and demo:** validate the calculations using clearly labelled sample shop data.

## 4. Core engineering safeguards

- Use SQLite transactions for operations that update multiple related records.
- Keep an append-only history for udhar transactions and stock movements where possible.
- Use idempotency keys to avoid duplicate Telegram updates, bill processing and SMS submissions.
- Store money as integer paise or use controlled decimal handling; avoid binary floating-point for financial calculations.
- Keep customer phone numbers and financial details private.
- Confirm uncertain OCR and voice extraction with the shopkeeper.
- Make the backend the source of truth for all calculations. Use Gemini for extraction and wording, not as the authority for financial totals.
- If a data source is unavailable, show a limited recommendation rather than fabricating values.

---

# Final Scope Summary

| Feature | What it delivers | Main implementation |
|---|---|---|
| **6. Dynamic Daily Business Summary** | Live daily sales, payment breakdown, customer-wise udhar, total outstanding and restock warnings, in Hinglish | Telegram + FastAPI + Sarvam/Gemini + SQLite queries |
| **7. Restock Advice** | What to buy, when to buy and suggested quantity, using shop history and local signals | Inventory calculations + Local Market Intelligence + festival/weather context + local price index |
| **8. Item-Level Profit** | Profit per unit and total profit per item sold | Supplier purchase cost + itemised sales + Python/SQL calculations |

**Scope note:** Feature 8 was initially described as a monthly approximate profit estimate (sales minus purchases). The current agreed PoC scope is simpler: item-level gross profit calculated as selling price minus purchase price per unit, multiplied by units sold. A full monthly net-profit calculation is not included.

**End of document.**
