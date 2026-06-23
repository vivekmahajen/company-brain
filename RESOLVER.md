# RESOLVER

> Generated canonical routing index (M5). Every skill MUST appear here.
> A compile that leaves a skill unroutable fails CI.

| Skill | Intents | Keywords | Priority |
|---|---|---|---|
| `handle-refund` — Handle a customer refund | issue a refund; customer wants their money back; process a chargeback reversal; refund an order | refund, money back, chargeback, reimburse, return payment | 100 |
| `handle-pricing-exception` — Handle a pricing exception | approve a discount; customer wants a lower price; grant a pricing exception; special pricing request | discount, pricing, price exception, deal desk, markdown, special pricing | 100 |
| `respond-to-incident` — Respond to a production incident | respond to an incident; production is down; service outage; page the on-call engineer | incident, outage, down, sev1, pager, on-call, post-mortem | 100 |
