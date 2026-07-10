# IMERP V GM Business Logic

This system is designed around exact real-world stock control for a phone shop.

## Inventory Brain

- Staff do not choose Serialized/Bulk manually.
- If serial/IMEI lines exist, each line becomes an exact unit.
- If serial/IMEI lines are empty, stock is treated as bulk quantity.
- Phone, laptop, tablet, watch, smartwatch and gaming items are expected to use exact units.
- Accessories can use bulk stock unless serials are typed.
- Duplicate IMEI/serial values are blocked.
- Restock never copies old IMEIs into the new restock field.
- Average cost is recalculated using weighted average on every restock.

## Retail Billing Brain

- Search by item name, SKU, full IMEI, or last 5 digits.
- Double-click a product to open all exact units.
- Double-click an available IMEI to add that specific unit to cart.
- Direct Sale Item is used for items bought from another shop and sold immediately.
- Direct sale items save item name, bought-from shop, reference/IMEI, buying cost, selling price and warranty on the invoice, but never change inventory stock.
- When invoice is saved, exact units are marked SOLD and linked to the invoice.
- Bulk stock is reduced by quantity and never goes below zero.
- Payment supports Cash, Card, Koko, bank/online transfers, credit and custom rows.

## Partner/Wholesale Brain

- Partner shops have profile pages, due lists, invoice history and payment history.
- Issue items using the same exact-unit picker as retail billing.
- Partner payments allocate FIFO to the oldest due invoice.
- Statement PDF and WhatsApp message show total due and due items.

## Finance Brain

- Admin sees revenue, COGS, profit, assets, receivables and payment method splits.
- Finance can show today/daily, weekly, monthly, annual and custom date-range sales.
- Direct sale buying costs are included in COGS, so profit stays accurate even when the item was never saved in inventory.
- Staff sees sold item quantity reports without sensitive money values.
- Inventory asset reports use available quantity and cost/average cost.

## Data Safety

- Invoice save and partner issue logic use database transactions.
- Stock is validated before invoice save.
- Backups include database and PDF folders.
- Sync creates safety backups before database replacement.
