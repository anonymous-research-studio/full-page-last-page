# Rendered examples: page 1 as the model saw it

From the episode logs of gpt-oss-120b: the output of the first call to the target tool, one episode per form, on a full first page with more rows behind it (plus the false end signals and self-contradicting pages of the main run, and the secondary forms). Rows are abbreviated to two; every other field, and any text after the JSON, is shown as the model saw it.

## `cursor_plus_note`, conflict `none`, placement `bottom` (main run)

```
{
 "results": [
  {
   "sku": "SKU-63406",
   "name": "Dalton heavy-duty monitor (gray, model 356)",
   "category": "Electronics",
   "price": 37.53,
   "in_stock": true
  },
  {
   "sku": "SKU-83109",
   "name": "Dalton portable monitor (gray, model 742)",
   "category": "Electronics",
   "price": 150.46,
   "in_stock": true
  },
  "... 18 more rows ..."
 ],
 "next_cursor": "G1iemu_T42FjbGHATpRl",
 "message": "Showing results 1-20 of 100."
}
```

## `total_count`, conflict `none`, placement `bottom` (main run)

```
{
 "results": [
  {
   "ticket_id": "TCK-20043",
   "status": "open",
   "priority": "low",
   "subject": "Request for invoice copy",
   "created": "2026-09-30"
  },
  {
   "ticket_id": "TCK-48569",
   "status": "open",
   "priority": "low",
   "subject": "Invoice shows wrong amount",
   "created": "2026-09-30"
  },
  "... 18 more rows ..."
 ],
 "total_count": 56
}
```

## `none`, conflict `none`, placement `bottom` (main run)

```
{
 "results": [
  {
   "order_id": "ORD-81478",
   "customer": "Skyler Haddad",
   "date": "2026-09-30",
   "item": "Keyboard",
   "amount": 197.62,
   "status": "cancelled"
  },
  {
   "order_id": "ORD-51500",
   "customer": "Skyler Haddad",
   "date": "2026-09-26",
   "item": "Bookshelf",
   "amount": 71.23,
   "status": "delivered"
  },
  "... 18 more rows ..."
 ]
}
```

## `total_count`, conflict `false_total`, placement `bottom` (main run)

```
{
 "results": [
  {
   "order_id": "ORD-55771",
   "customer": "Taylor Brooks",
   "date": "2026-09-30",
   "item": "Monitor stand",
   "amount": 155.79,
   "status": "processing"
  },
  {
   "order_id": "ORD-94797",
   "customer": "Taylor Brooks",
   "date": "2026-09-29",
   "item": "USB-C cable",
   "amount": 19.95,
   "status": "shipped"
  },
  "... 18 more rows ..."
 ],
 "total_count": 20
}
```

## `next_cursor`, conflict `none`, placement `bottom` (main run)

```
{
 "results": [
  {
   "sku": "SKU-56966",
   "name": "Ivers compact notebook (white, model 418)",
   "category": "Stationery",
   "price": 97.63,
   "in_stock": false
  },
  {
   "sku": "SKU-71788",
   "name": "Arden portable notebook (black, model 970)",
   "category": "Stationery",
   "price": 166.39,
   "in_stock": true
  },
  "... 18 more rows ..."
 ],
 "next_cursor": "98YyLsqR683pr5s9t364"
}
```

## `nl_note_json`, conflict `none`, placement `bottom` (main run)

```
{
 "results": [
  {
   "sku": "SKU-39908",
   "name": "Garrow classic bottle (red, model 740)",
   "category": "Kitchen",
   "price": 102.37,
   "in_stock": false
  },
  {
   "sku": "SKU-93749",
   "name": "Fenwick adjustable bottle (blue, model 489)",
   "category": "Kitchen",
   "price": 111.87,
   "in_stock": true
  },
  "... 18 more rows ..."
 ],
 "message": "Showing results 1-20 of 68."
}
```

## `next_cursor`, conflict `false_end_cursor`, placement `bottom` (main run)

```
{
 "results": [
  {
   "ticket_id": "TCK-2096",
   "status": "open",
   "priority": "low",
   "subject": "Discount code not working",
   "created": "2026-09-30"
  },
  {
   "ticket_id": "TCK-42827",
   "status": "open",
   "priority": "high",
   "subject": "Delivery delayed",
   "created": "2026-09-30"
  },
  "... 18 more rows ..."
 ],
 "next_cursor": null
}
```

## `has_more`, conflict `none`, placement `bottom` (main run)

```
{
 "results": [
  {
   "order_id": "ORD-80021",
   "customer": "Avery Lin",
   "date": "2026-09-30",
   "item": "Picture frame",
   "amount": 14.03,
   "status": "shipped"
  },
  {
   "order_id": "ORD-39488",
   "customer": "Avery Lin",
   "date": "2026-09-29",
   "item": "Wireless mouse",
   "amount": 40.59,
   "status": "delivered"
  },
  "... 18 more rows ..."
 ],
 "has_more": true
}
```

## `has_more`, conflict `false_end`, placement `bottom` (main run)

```
{
 "results": [
  {
   "sku": "SKU-26243",
   "name": "Garrow adjustable lamp (white, model 380)",
   "category": "Lighting",
   "price": 128.77,
   "in_stock": false
  },
  {
   "sku": "SKU-11802",
   "name": "Dalton slim lamp (gray, model 446)",
   "category": "Lighting",
   "price": 186.86,
   "in_stock": true
  },
  "... 18 more rows ..."
 ],
 "has_more": false
}
```

## `next_cursor`, conflict `visible_conflict_note`, placement `bottom` (main run)

```
{
 "results": [
  {
   "order_id": "ORD-30468",
   "customer": "Quinn Larsen",
   "date": "2026-09-30",
   "item": "Desk lamp",
   "amount": 165.86,
   "status": "refunded"
  },
  {
   "order_id": "ORD-79586",
   "customer": "Quinn Larsen",
   "date": "2026-09-29",
   "item": "Phone charger",
   "amount": 24.45,
   "status": "shipped"
  },
  "... 18 more rows ..."
 ],
 "next_cursor": null,
 "message": "Showing results 1-20 of 69."
}
```

## `has_more`, conflict `visible_conflict_total`, placement `bottom` (main run)

```
{
 "results": [
  {
   "order_id": "ORD-47382",
   "customer": "Jordan Patel",
   "date": "2026-09-30",
   "item": "Phone charger",
   "amount": 187.85,
   "status": "shipped"
  },
  {
   "order_id": "ORD-25094",
   "customer": "Jordan Patel",
   "date": "2026-09-28",
   "item": "Plant pot",
   "amount": 77.1,
   "status": "cancelled"
  },
  "... 18 more rows ..."
 ],
 "has_more": false,
 "total_count": 69
}
```

## `nl_note_json`, conflict `false_note`, placement `bottom` (main run)

```
{
 "results": [
  {
   "sku": "SKU-26243",
   "name": "Garrow adjustable lamp (white, model 380)",
   "category": "Lighting",
   "price": 128.77,
   "in_stock": false
  },
  {
   "sku": "SKU-11802",
   "name": "Dalton slim lamp (gray, model 446)",
   "category": "Lighting",
   "price": 186.86,
   "in_stock": true
  },
  "... 18 more rows ..."
 ],
 "message": "Showing results 1-20 of 20."
}
```

## `nl_note`, conflict `none`, placement `bottom` (secondary run)

```
{
 "results": [
  {
   "order_id": "ORD-80822",
   "customer": "Casey Okafor",
   "date": "2026-09-30",
   "item": "File folders",
   "amount": 239.83,
   "status": "delivered"
  },
  {
   "order_id": "ORD-17208",
   "customer": "Casey Okafor",
   "date": "2026-09-27",
   "item": "Wall clock",
   "amount": 90.74,
   "status": "shipped"
  },
  "... 18 more rows ..."
 ]
}
Showing results 1-20 of 71.
```

## `link_header`, conflict `none`, placement `bottom` (secondary run)

```
{
 "results": [
  {
   "order_id": "ORD-61047",
   "customer": "Jordan Patel",
   "date": "2026-09-30",
   "item": "Paper shredder",
   "amount": 143.58,
   "status": "refunded"
  },
  {
   "order_id": "ORD-86032",
   "customer": "Jordan Patel",
   "date": "2026-09-28",
   "item": "Webcam",
   "amount": 163.31,
   "status": "shipped"
  },
  "... 18 more rows ..."
 ],
 "headers": {
  "Link": "<https://api.example.com/v1/orders?customer=Jordan+Patel&cursor=RbTVgdxQFdapTFZr4Lxc&limit=20>; rel=\"next\""
 }
}
```

## `placeholder_row`, conflict `none`, placement `bottom` (secondary run)

```
{
 "results": [
  {
   "sku": "SKU-14084",
   "name": "Bexley compact cable (red, model 973)",
   "category": "Electronics",
   "price": 183.68,
   "in_stock": true
  },
  {
   "sku": "SKU-54428",
   "name": "Ivers basic cable (white, model 176)",
   "category": "Electronics",
   "price": 163.51,
   "in_stock": true
  },
  "... 18 more rows ...",
  "[… 58 more not shown]"
 ]
}
```

## `has_more`, conflict `none`, placement `top` (secondary run)

```
{
 "has_more": true,
 "results": [
  {
   "sku": "SKU-65465",
   "name": "Arden classic chair (green, model 415)",
   "category": "Furniture",
   "price": 132.48,
   "in_stock": true
  },
  {
   "sku": "SKU-85361",
   "name": "Halden compact chair (gray, model 266)",
   "category": "Furniture",
   "price": 106.77,
   "in_stock": true
  },
  "... 18 more rows ..."
 ]
}
```

## `page_info`, conflict `none`, placement `bottom` (secondary run)

```
{
 "results": [
  {
   "ticket_id": "TCK-95698",
   "status": "open",
   "priority": "low",
   "subject": "Invoice shows wrong amount",
   "created": "2026-09-30"
  },
  {
   "ticket_id": "TCK-17124",
   "status": "open",
   "priority": "low",
   "subject": "Discount code not working",
   "created": "2026-09-27"
  },
  "... 18 more rows ..."
 ],
 "pageInfo": {
  "hasNextPage": true,
  "endCursor": "y9WhCo6z5w_hxItuzg0s"
 }
}
```
