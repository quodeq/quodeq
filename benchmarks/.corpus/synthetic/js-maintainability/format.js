function formatCurrency(amount, currency) {
  return `${amount.toFixed(2)} ${currency}`;
}

module.exports = { formatCurrency };
