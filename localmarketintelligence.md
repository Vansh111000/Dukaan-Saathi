# Dukaan Saathi — Local Market Intelligence

## Features 9 and 10

We're building two connected features that help shopkeepers make better purchasing and stocking decisions using anonymised information collected from other participating shops.

1. **Feature 9 — Local Price Index:** Understand wholesale prices in the neighbourhood and compare them with the shopkeeper's own purchase prices.
2. **Feature 10 — Neighbourhood Alerts:** Detect unusual increases in purchasing activity across nearby shops and notify relevant shopkeepers about products they may want to stock up on.

Both features use the same purchase-bill data pipeline, product catalogue, shop profiles and geographical intelligence.

**Core concept:** We collect purchase information from shops, aggregate it geographically, analyse the data, and provide useful insights without revealing individual shops' business information.

We are not using external retail datasets. The intelligence develops from bills uploaded by participating shops.

---

## 1. What exactly are we building?

### Feature 9 — Local Price Index

- Local wholesale price median
- Minimum and maximum observed prices
- Individual shop's purchase price comparison
- Weekly price increase/decrease

### Feature 10 — Neighbourhood Alerts

- Detect unusual purchasing increases
- Identify how many shops are contributing
- Identify shops selling the relevant product
- Send personalised restocking suggestions

---

## 2. Complete implementation architecture

1. **Shop registration**
   - Shop category, products sold, pincode, locality, optional coordinates and consent.
2. **Purchase bill collection**
   - Shopkeeper uploads wholesale bill through Telegram.
3. **Bill extraction**
   - Gemini Vision extracts products, quantities, units, brands and prices.
4. **Product normalisation**
   - Standard product IDs, fuzzy matching, unit conversion and validation.
5. **PostgreSQL database**
   - Store shop profiles, bills, purchase items and product records.
6. **Two intelligence engines**
   - **Price index engine:** median, range, price comparisons and trends.
   - **Demand intelligence engine:** purchase aggregation and spike detection.
7. **Geographical and shop relevance engine**
   - Nearby-shop identification, category filters, vector search and fuzzy relevance.
8. **Privacy filter**
   - Minimum independent-shop threshold, aggregation and consent checks.
9. **Telegram notifications**
   - Personalised price reports and neighbourhood alerts.

---

## 3. What information do we need from shopkeepers?

There are three categories of inputs.

### A. Registration information

| Input | Required? | Purpose |
|---|---|---|
| Shop name | Yes | Shop identification |
| Pincode | Yes | Broad geographical grouping |
| Locality/area | Yes | Neighbourhood identification |
| Shop category | Yes | Grocery, general store, stationery, etc. |
| Products sold | Yes | Decide which alerts are relevant |
| Shop coordinates | Optional | Accurate distance calculation |
| Neighbourhood data-sharing consent | Explicit opt-in | Permission to contribute to pooled intelligence |
| Shop size | Optional | Additional purchasing context |

The products-sold field should support multiple selections and manual additions.

Examples: rice, cooking oil, sugar, pulses, snacks, beverages, personal care and household products.

### B. Purchase bill information

This is the most important input.

| Field | Example |
|---|---|
| Shop ID | SHOP_001 |
| Product | Fortune Sunflower Oil |
| Brand | Fortune |
| Quantity | 20 |
| Unit | Litres |
| Pack size | 1 litre |
| Total price | ₹2,800 |
| Unit price | ₹140/litre |
| Purchase date | 31 October 2026 |
| Bill ID | BILL_001 |

The shopkeeper only needs to upload the bill. The system extracts these fields automatically and requests confirmation when necessary.

### C. Optional ongoing information

- Products currently out of stock.
- Whether the shop still sells a particular product.
- Whether a purchase is for this shop or another branch.
- Notification preferences.
- Corrections to incorrectly extracted bills.

---

## 4. How do we identify nearby shops?

Use **hybrid geographical identification**.

| Information | Role |
|---|---|
| Pincode | Initial geographical grouping |
| Locality name | Human-readable area |
| Latitude and longitude | Precise distance calculation |
| Distance radius | Decide which shops are nearby |

### How it works

During registration, the shopkeeper enters their pincode and locality. We optionally request location sharing through Telegram.

We receive coordinates and calculate distance using the Haversine formula or PostGIS.

For the first version:

- Start with a 2 km radius.
- Find all participating shops within that radius.
- Filter shops by relevant product and category.
- If there are insufficient contributors, expand the radius gradually.
- Clearly identify the broader area used for the resulting insight.

The 2 km radius is configurable, not a fixed definition of every neighbourhood.

**Technology:** Telegram Bot API + PostgreSQL + PostGIS.

We should never reveal exact shop coordinates to other shopkeepers.

---

## 5. Feature 9 — Local Price Index: Implementation logic

### What it does

It calculates local wholesale prices using comparable purchase bills from multiple participating shops.

### Step-by-step logic

| Step | What happens | Implementation |
|---|---|---|
| 1 | Collect wholesale bills | Telegram + FastAPI |
| 2 | Extract prices and products | Gemini Vision |
| 3 | Match equivalent products | Product taxonomy + RapidFuzz |
| 4 | Standardise quantities and units | Python unit converter |
| 5 | Group comparable purchases by locality and week | PostgreSQL |
| 6 | Calculate median, minimum and maximum | SQL + Python |
| 7 | Compare individual shop price with local median | Python |
| 8 | Send price report | Telegram Bot API |

### Example calculation

Five shops purchase the same comparable sunflower oil product:

₹140, ₹143, ₹138, ₹145, ₹142 per litre.

Sorted:

₹138, ₹140, ₹142, ₹143, ₹145.

\[
\text{Local median}=₹142/L
\]

If another shop purchases at ₹150/L:

\[
\text{Difference}=150-142=₹8
\]

\[
\text{Percentage difference}
=\frac{8}{142}\times100=5.63\%
\]

The shopkeeper receives a comparison showing:

- Their purchase price: ₹150/L
- Local median: ₹142/L
- Local range: ₹138–₹145/L
- Difference: 5.63% above the local median
- Number of contributing shops: 5

### Price reliability rules

- Minimum 5 independent shops per product and reporting period; aim for 10 where possible.
- Compare the same brand/variant and pack size where applicable.
- Standardise units and account for taxes, discounts and delivery charges where possible.
- Use median rather than just average.
- Do not reveal individual prices or shop identities.
- Suppress results when there are insufficient contributors.

A higher price does not necessarily mean a shopkeeper is being overcharged. Supplier distance, credit terms, delivery charges, discounts and purchase volume can affect prices. Present this as a comparison, not an accusation.

---

## 6. Feature 10 — Neighbourhood Alerts: Implementation logic

### What it does

It detects unusual increases in purchasing activity across nearby shops and informs other relevant shops.

### Step 1 — Aggregate purchasing activity

Group purchases by:

- Product
- Locality
- Week
- Independent contributing shops

Example:

| Shop | Sunflower oil purchased |
|---|---:|
| A | 100 L |
| B | 80 L |
| C | 120 L |
| D | 90 L |
| E | 110 L |
| Other shops | 200 L |
| **Total** | **700 L** |

### Step 2 — Calculate the historical baseline

Suppose previous weekly purchases were:

400 L, 420 L, 390 L and 410 L.

\[
\text{Baseline}=\frac{400+420+390+410}{4}=405L
\]

Current purchases = 700 L.

\[
\text{Increase}=\frac{700-405}{405}\times100=72.84\%
\]

This indicates a significant purchasing increase.

### Step 3 — Apply alert conditions

Initial configurable rules:

| Condition | Starting threshold |
|---|---|
| Purchase increase | At least 30% above baseline |
| Independent shops | At least 5 |
| Total volume | Product-specific minimum |
| Data quality | Sufficient valid purchase records |
| Recipient relevance | Shop sells the product |

All required conditions must be satisfied before generating an alert. Thresholds will need tuning as real data accumulates.

### Step 4 — Identify shops that should receive alerts

First use geographical and category filters. Then use vector similarity and fuzzy relevance if needed.

| Shop | Inventory | Receive oil alert? |
|---|---|---|
| A | Grocery, rice, oil | Yes |
| B | General store, oil, snacks | Yes |
| C | Stationery | No |
| D | Bakery | Usually no |
| E | Grocery, pulses, oil | Yes |

### Step 5 — Generate and deliver the alert

Example:

> **Dukaan Saathi — Possible purchasing spike**
>
> **Sunflower oil purchasing is up in your area!**
>
> Multiple nearby grocery and general stores have increased their sunflower oil purchases this week.
>
> - Purchasing volume is approximately 73% above the recent baseline.
> - At least 5 independent shops contributed.
> - This product matches your shop's inventory profile.
>
> **Suggestion:** Check your current stock and consider restocking if required.

Purchasing patterns are an indicator, not proof of increased consumer demand.

---

## 7. Where vector search and fuzzy logic fit

These are advanced components, not the foundation of the system.

| Component | Technology | Purpose |
|---|---|---|
| Product matching | RapidFuzz | Match variations in product names |
| Embedding generation | Sentence Transformers | Represent product/shop profiles |
| Vector retrieval | Qdrant | Find semantically similar products and shops |
| Fuzzy relevance | scikit-fuzzy | Combine similarity, locality and confidence signals |

### Vector search

Generate embeddings from each shop's product catalogue.

Example:

```text
Shop A:
grocery, rice, cooking oil, pulses, sugar

Shop B:
stationery, notebooks, pens

Shop C:
grocery, beverages, cooking oil, snacks
```

Qdrant helps retrieve shops with relevant product profiles.

### Fuzzy logic

Combine:

- Product relevance
- Shop similarity
- Locality proximity
- Confidence in purchasing spike
- Strength of purchasing increase

The fuzzy engine can classify alert relevance as Low, Medium or High.

**Important architecture decision:** Calculate purchasing trends from all eligible shops in the geographical area. Use vector search only to identify relevant recipients, not to determine the total neighbourhood trend.

For the first version, category and product filters may be sufficient. Add Qdrant and fuzzy logic after the core system works.

---

## 8. Database requirements

We need these core PostgreSQL tables.

| Table | What it stores |
|---|---|
| `shops` | Shop ID, category, pincode, locality, coordinates |
| `shop_products` | Products each shop sells |
| `products` | Standard product catalogue, brand, variant and units |
| `purchase_bills` | Uploaded bill information |
| `purchase_items` | Extracted product, quantity, unit and price |
| `area_product_weekly_stats` | Aggregated local purchase statistics |
| `price_indices` | Median, minimum, maximum and contributor count |
| `demand_alerts` | Detected purchasing spikes |
| `shop_alert_preferences` | Notification and consent preferences |

PostgreSQL stores the structured business records. PostGIS handles geographical queries. Qdrant stores embeddings if and when we introduce vector search.

We should retain original extracted bill data with restricted access and make only privacy-filtered aggregates available to the intelligence engines and shopkeepers.

---

## 9. Technology stack and what each part does

| Layer | Technology | Responsibility |
|---|---|---|
| User interface | Telegram Bot API | Bill uploads, queries and notifications |
| Backend | FastAPI | APIs and business logic |
| OCR / vision | Gemini Vision | Understand bill photographs |
| Product normalisation | RapidFuzz | Match product descriptions |
| Unit conversion | Python | Standardise quantities |
| Database | PostgreSQL | Store structured data |
| Geospatial | PostGIS | Find nearby shops |
| Analytics | Python, SQL, Pandas | Calculate indices and purchasing spikes |
| Embeddings | Sentence Transformers | Shop/product similarity |
| Vector database | Qdrant | Similarity retrieval |
| Fuzzy logic | scikit-fuzzy | Alert relevance scoring |
| Scheduler | APScheduler | Weekly background calculations |
| Notifications | Telegram Bot API | Deliver results |

---

## 10. Automated background processing

We shouldn't recalculate everything whenever a shopkeeper sends a message. Use scheduled jobs.

| Job | When it runs | What it does |
|---|---|---|
| Bill extraction | On bill upload | Extracts structured information |
| Product normalisation | After extraction | Maps products to standard IDs |
| Price index calculation | Weekly | Calculates local price statistics |
| Purchasing spike detection | Weekly | Compares current activity with baseline |
| Shop relevance matching | After spike detection | Finds relevant nearby shops |
| Alert generation | After filtering | Sends notifications |

For the prototype, APScheduler is enough. A dedicated job queue can be introduced later if needed.

---

## 11. Privacy and reliability requirements

These are essential, not optional enhancements.

- Explicit opt-in for neighbourhood data contribution.
- Allow shops to withdraw consent.
- Require at least 5 independent shops for published aggregates; aim for 10 where feasible.
- Never disclose shop names, exact purchase quantities, supplier identities or raw bills.
- Apply contributor thresholds separately to each product and reporting period.
- Prevent duplicate bills and repeated contributions from one shop from inflating the contributor count.
- Do not expose exact shop coordinates.
- Restrict access to raw transaction data.
- Show the time period and contributor count for insights.
- Do not describe purchasing spikes as confirmed consumer demand.

---

## 12. Development roadmap — what to build first

### Phase 1 — Registration and location

Build:
- Shop registration through Telegram
- Pincode and locality capture
- Optional coordinate sharing
- Shop category and product selection
- Consent management
- PostgreSQL and PostGIS setup

**Output:** We know which shops exist, what they sell and approximately where they are.

### Phase 2 — Bill processing

Build:
- Telegram bill uploads
- Gemini Vision extraction
- Structured Pydantic schemas
- Product catalogue
- RapidFuzz matching
- Unit conversion
- Bill confirmation and validation

**Output:** We have reliable structured purchase records.

### Phase 3 — Local price index

Build:
- Geographical grouping
- Comparable product filtering
- Weekly price aggregation
- Median, range and price comparison
- Contributor thresholds

**Output:** Feature 9 works end to end.

### Phase 4 — Purchasing spike detection

Build:
- Weekly quantity aggregation
- Four-week moving-average baseline
- Percentage increase calculation
- Minimum volume and contributor checks

**Output:** We can detect candidate purchasing spikes.

### Phase 5 — Shop relevance engine

Build:
- Shop inventory profiles
- Geographic and category filters
- Sentence Transformer embeddings
- Qdrant integration
- Fuzzy relevance scoring
- Privacy filtering

**Output:** We know which shops should receive which alerts.

### Phase 6 — Notifications and testing

Build:
- Telegram price-index queries
- Personal price comparisons
- Neighbourhood alert messages
- Notification preferences
- Scheduled jobs
- End-to-end testing

**Output:** Features 9 and 10 work end to end.

---

## 13. Hackathon demonstration plan

Use clearly labelled simulated shops and bills to demonstrate the pipeline. This is test data, not a production dependency.

| Demo action | Expected outcome |
|---|---|
| Register 10 shops in a locality | Shops receive profiles and locations |
| Upload wholesale bills | Gemini extracts product and price data |
| Upload comparable oil bills | Local median and range are calculated |
| Add a shop with a higher purchase price | Personal price comparison appears |
| Increase oil purchases across multiple shops | Spike detection triggers |
| Add stationery shops | They are excluded from oil alerts |
| Run privacy checks | Only eligible aggregate information is shared |

---

## 14. Final requirements checklist

### Shop onboarding and location

- [ ] Telegram registration flow
- [ ] Pincode and locality fields
- [ ] Optional Telegram location sharing
- [ ] Shop category and products sold
- [ ] Explicit neighbourhood data consent
- [ ] PostGIS location storage

### Purchase data pipeline

- [ ] Telegram bill upload
- [ ] Gemini Vision integration
- [ ] Structured extraction schema
- [ ] Product taxonomy
- [ ] RapidFuzz matching
- [ ] Unit and pack-size normalisation
- [ ] Bill validation and duplicate detection

### Local Price Index

- [ ] Comparable product filtering
- [ ] Locality-based price aggregation
- [ ] Median, minimum and maximum
- [ ] Individual price comparison
- [ ] Weekly price trend
- [ ] Minimum contributor threshold

### Neighbourhood Alerts

- [ ] Weekly quantity aggregation
- [ ] Historical purchasing baseline
- [ ] Spike detection thresholds
- [ ] Minimum volume and shop count
- [ ] Shop relevance filtering
- [ ] Alert generation and delivery

### Advanced intelligence and safeguards

- [ ] Sentence Transformer embeddings
- [ ] Qdrant vector retrieval
- [ ] Fuzzy relevance scoring
- [ ] Privacy filtering
- [ ] Consent withdrawal
- [ ] Scheduled background jobs

---

## 15. Final recommended implementation scope

| Priority | Component | Decision |
|---|---|---|
| P0 | Shop registration and location | Build first |
| P0 | Bill extraction and normalisation | Build first |
| P0 | PostgreSQL and PostGIS | Build first |
| P0 | Local price index | Build first |
| P0 | Purchasing spike detection | Build first |
| P0 | Privacy and consent | Build first |
| P1 | Shop relevance filtering | Category + geographical filters |
| P1 | Telegram notifications | Build with alert engine |
| P2 | Sentence Transformers + Qdrant | Add after basic matching |
| P2 | Fuzzy logic | Add after initial alert scoring works |

**The most important thing to understand:** The intelligence doesn't come from Gemini, Qdrant or fuzzy logic alone. It comes from collecting reliable purchase information from multiple shops, standardising it, grouping it geographically and applying meaningful statistical calculations.

That's the actual product we're building: a **neighbourhood-level business intelligence system for small retailers**.
