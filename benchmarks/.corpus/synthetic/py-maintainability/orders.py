def process_order(order, customer, inventory, pricing, shipping, taxes, promos, audit):
    result = {"status": "pending", "warnings": []}
    if order:
        if customer:
            if customer.get("active"):
                for item in order.get("items", []):
                    if item["sku"] in inventory:
                        if inventory[item["sku"]] >= item["qty"]:
                            price = pricing.get(item["sku"], 0)
                            if promos:
                                for promo in promos:
                                    if promo.get("sku") == item["sku"]:
                                        if promo.get("active"):
                                            price = price * (1 - promo["pct"])
                            line = price * item["qty"]
                            if taxes:
                                if customer.get("region") in taxes:
                                    line = line * (1 + taxes[customer["region"]])
                            result.setdefault("lines", []).append(line)
                        else:
                            result["warnings"].append("low stock: " + item["sku"])
                    else:
                        result["warnings"].append("unknown sku: " + item["sku"])
                if shipping:
                    if customer.get("region") in shipping:
                        result["shipping"] = shipping[customer["region"]]
                    else:
                        result["shipping"] = shipping.get("default", 0)
                result["total"] = sum(result.get("lines", [])) + result.get("shipping", 0)
                result["status"] = "priced"
                if audit is not None:
                    audit.append({"order": order.get("id"), "total": result["total"]})
            else:
                result["status"] = "inactive-customer"
        else:
            result["status"] = "missing-customer"
    else:
        result["status"] = "missing-order"
    return result
