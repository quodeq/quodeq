function buildReport(orders, customers, taxes, shipping, promos, locale, currency, audit, verbose) {
  const lines = [];
  for (const order of orders) {
    const customer = customers[order.customerId];
    if (customer) {
      if (customer.active) {
        let total = 0;
        for (const item of order.items) {
          let price = item.price * item.qty;
          if (promos && promos[item.sku]) {
            if (promos[item.sku].active) {
              price = price * (1 - promos[item.sku].pct);
            }
          }
          if (taxes && taxes[customer.region]) {
            price = price * (1 + taxes[customer.region]);
          }
          total += price;
        }
        if (shipping && shipping[customer.region]) {
          total += shipping[customer.region];
        }
        if (verbose) {
          lines.push(`${customer.name} (${locale}/${currency}): ${total}`);
        } else {
          lines.push(`${customer.name}: ${total}`);
        }
        if (audit) {
          audit.push({ order: order.id, total });
        }
      }
    }
  }
  return lines.join("\n");
}

module.exports = { buildReport };
