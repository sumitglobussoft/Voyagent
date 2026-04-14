# Offer cache — why it's not in Postgres

Amadeus Self-Service booking (`/v1/booking/flight-orders`) requires the
caller to re-submit the original flight-offer JSON that came back from
shopping. Those offers expire in 15–30 minutes, so we cache them in
Redis with a TTL, keyed by the canonical `Fare.id` the runtime mints
during `search`. See `services/agent_runtime/src/voyagent_agent_runtime/offer_cache.py`
for the `RedisOfferCache` implementation and
`drivers/amadeus/driver.py::AmadeusDriver.create` for the consumer.

Postgres would be the wrong place for this: offers are ephemeral,
high-churn, and only useful to the driver that cached them. Redis gives
us native TTL eviction and avoids vacuum pressure on the audit tables.
The audit trail still captures every successful/failed `create` call.
