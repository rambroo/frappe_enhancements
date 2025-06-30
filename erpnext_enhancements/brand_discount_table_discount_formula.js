var brandDiscounts = {};
var isBrandDiscountTriggered = false;

// Utility function to safely convert values and prevent NaN
function safeNumber(value, defaultValue = 0) {
    if (value === null || value === undefined || isNaN(value) || !isFinite(value)) {
        return defaultValue;
    }
    return parseFloat(value) || defaultValue;
}

// Utility function to safely format numbers
function safeFormat(value, decimals = 2) {
    const num = safeNumber(value);
    return num.toFixed(decimals);
}


frappe.ui.form.on("Quotation", {
    refresh: function(frm) {
        // Add a button in the form header
        frm.add_custom_button(__('Update Brand Discounts'), function() {
            frm.trigger("update_brand_discounts");
            setApplyDiscount(frm);
        }).addClass('btn-primary'); // Make it visually distinct
    },
    
    // UPDATED: Modified before_save to use our new logic
    before_save: function(frm) {
        // Clean any NaN values before saving
        cleanNaNValues(frm);
        
        // Update brand discounts using the same logic as the button
        update_brand_discounts_for_save(frm);
        setApplyDiscount(frm);
    },
    
    onload: function(frm) {
        if (!isBrandDiscountTriggered) {
            // Fetch all pricing rules and store discount percentages
            frappe.call({
                method: "frappe.client.get_list",
                args: {
                    doctype: "Pricing Rule",
                    fields: ["name", "discount_percentage"],
                    limit_page_length: 1000
                },
                async: false,
                callback: function(response) {
                    if (response.message) {
                        response.message.forEach(rule => {
                            getBrandFromPricingRule(rule.name, rule.discount_percentage, brandDiscounts);
                        });
                    }
                }
            });
        }
    },
    
    validate: function(frm) {
        // Clean NaN values before validation
        cleanNaNValues(frm);
        
        let exceeds_discount = false;

        // Check manual discounts in the custom discount table
        (frm.doc.custom_dicount_table || []).forEach(row => {
            let brand = row.brand;
            let manual_discount = safeNumber(row.manual_discount);

            if (brand && brandDiscounts[brand] !== undefined) {
                if (manual_discount > brandDiscounts[brand]) {
                    exceeds_discount = true;
                }
            }
        });

        if (exceeds_discount) {
            if ("custom_requires_approval_for_discount" in frm.doc) {
                frm.set_value("custom_requires_approval_for_discount", 1);
            } else {
                console.error("Error: Field 'custom_requires_approval' not found in Quotation Doctype!");
            }

            if (frm.doc.custom_requires_approval_for_discount) {
                frm.refresh();
            }
        }
    },

    // Main update function with NaN prevention
    update_brand_discounts: function(frm) {
        console.log("1");

        if (!frm.doc.items || frm.doc.items.length === 0) {
            frm.clear_table("custom_dicount_table");
            frm.refresh_field("custom_dicount_table");
            console.log("2");
            return;
        }

        let brand_totals = {};
        let manual_discounts = {};

        // Store existing manual discounts from brand table
        if (frm.doc.custom_dicount_table) {
            frm.doc.custom_dicount_table.forEach(row => {
                manual_discounts[row.brand] = safeNumber(row.manual_discount);
            });
        }

        // Calculate brand totals using CURRENT item discounts (preserve manual changes)
        frm.doc.items.forEach(item => {
            if (item.brand) {
                if (!brand_totals[item.brand]) {
                    brand_totals[item.brand] = {
                        value: 0,
                        total_discount: 0,
                        item_count: 0,
                        manual_discount: manual_discounts[item.brand] || 0
                    };
                }
                
                const itemValue = safeNumber(item.price_list_rate) * safeNumber(item.qty);
                const itemDiscount = safeNumber(item.discount_percentage);
                
                brand_totals[item.brand].value += itemValue;
                brand_totals[item.brand].total_discount += itemDiscount;
                brand_totals[item.brand].item_count += 1;
            }
        });

        console.log(brand_totals);

        frappe.call({
            method: "erpnext_mxt.custom_functions.brand_discount.get_brand_discounts",
            args: {
                brand_list: Object.keys(brand_totals)
            },
            callback: function(r) {
                if (r.message && Array.isArray(r.message) && r.message.length > 0) {
                    frm.clear_table("custom_dicount_table");
                    console.log("3");

                    r.message.forEach(rule => {
                        if (brand_totals[rule.brand]) {
                            brand_totals[rule.brand].max_discount_percentage = safeNumber(rule.discount_percentage);
                            brand_totals[rule.brand].default_discount_percentage = safeNumber(rule.custom_default_discount_percentage);
                            
                            // Calculate WEIGHTED average discount from current items - PREVENT NaN
                            brand_totals[rule.brand].average_discount = 
                                brand_totals[rule.brand].value > 0 ? 
                                safeNumber(brand_totals[rule.brand].total_discount / brand_totals[rule.brand].value * 100) : 0;

                            // Use default discount if no items have discounts yet
                            if (brand_totals[rule.brand].average_discount === 0 && brand_totals[rule.brand].manual_discount === 0) {
                                brand_totals[rule.brand].average_discount = brand_totals[rule.brand].default_discount_percentage;
                                
                                // Apply default discount to items that don't have any discount
                                frm.doc.items.forEach(item => {
                                    if (item.brand === rule.brand && safeNumber(item.discount_percentage) === 0) {
                                        frappe.model.set_value(item.doctype, item.name, 'discount_percentage', brand_totals[rule.brand].default_discount_percentage);
                                    }
                                });
                            }

                            // Use manual discount if set, otherwise use calculated average
                            let applied_discount = brand_totals[rule.brand].manual_discount > 0 ? 
                                brand_totals[rule.brand].manual_discount : 
                                brand_totals[rule.brand].average_discount;

                            brand_totals[rule.brand].discount_amount = safeNumber(
                                (brand_totals[rule.brand].value * applied_discount) / 100
                            );
                        }
                    });

                    Object.keys(brand_totals).forEach(brand => {
                        let row = frm.add_child("custom_dicount_table");
                        console.log("8");
                        if (row) {
                            row.brand = brand;
                            row.value = safeFormat(brand_totals[brand].value);
                            row.disc_ = safeFormat(brand_totals[brand].average_discount);
                            row.discount_amount = safeFormat(brand_totals[brand].discount_amount);
                            row.total_value = safeFormat(brand_totals[brand].value - brand_totals[brand].discount_amount);
                            row.max_discount = safeFormat(brand_totals[brand].max_discount_percentage);
                            row.applied_discount = safeFormat(brand_totals[brand].average_discount);
                            
                            // Set manual_discount to match disc_ when it's calculated from item averages
                            if (brand_totals[brand].manual_discount <= 0 && brand_totals[brand].average_discount > 0) {
                                row.manual_discount = safeFormat(brand_totals[brand].average_discount);
                            } else {
                                row.manual_discount = safeFormat(brand_totals[brand].manual_discount);
                            }
                            
                            console.log(row);
                        }
                    });

                    frm.refresh_field("custom_dicount_table");
                    frm.refresh_field("items");
                    console.log("Table Refreshed");
                } else {
                    console.log("Refresh");
                    frm.clear_table("custom_dicount_table");
                    frm.refresh_field("custom_dicount_table");
                }
            }
        });

        frm.refresh();
    }
});


// Fetch brand separately for each Pricing Rule
function getBrandFromPricingRule(pricingRuleName, discountPercentage, brandDiscounts) {
    frappe.call({
        method: "frappe.client.get",
        args: {
            doctype: "Pricing Rule",
            name: pricingRuleName
        },
        async: true,
        callback: function(response) {
            //console.log("get response", response.message)
            if (response.message && response.message.brands) {
                // Store discount percentage for the brand
                brandDiscounts[response.message.brands[0].brand] = safeNumber(discountPercentage);
            }

        }
    });
}

function update_brand_discounts_sync(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) return;

    const brand_totals = {};
    const manual_discounts = {};

    // Get manual discounts
    (frm.doc.custom_dicount_table || []).forEach(row => {
        manual_discounts[row.brand] = row.manual_discount || 0;
    });

    // Compute brand totals
    (frm.doc.items || []).forEach(item => {
        if (!item.brand) return;

        if (!brand_totals[item.brand]) {
            brand_totals[item.brand] = {
                value: 0,
                discount_percentage: 0,
                manual_discount: manual_discounts[item.brand] || 0
            };
        }

        brand_totals[item.brand].value += (item.price_list_rate * item.qty);
    });

    // Assume brandDiscounts is preloaded with { brand: discount_percentage } format
    frm.clear_table("custom_dicount_table");
    Object.keys(brand_totals).forEach(brand => {
        const brandData = brand_totals[brand];
        const max_discount = brandDiscounts[brand] || 0;
        const applied_discount = brandData.manual_discount > 0 ? brandData.manual_discount : max_discount;
        const discount_amount = (brandData.value * applied_discount) / 100;
        const total_value = brandData.value - discount_amount;

        let row = frm.add_child("custom_dicount_table", {
            brand: brand,
            value: brandData.value.toFixed(2),
            max_discount: max_discount,
            disc_: applied_discount,
            manual_discount: brandData.manual_discount,
            discount_amount: discount_amount.toFixed(2),
            total_value: total_value.toFixed(2)
        });
    });

    // IMPORTANT: Update the items' discount percentages
    (frm.doc.items || []).forEach(row => {
        const discount_row = frm.doc.custom_dicount_table.find(d => d.brand === row.brand);
        if (discount_row) {
            const discount_value = discount_row.manual_discount > 0 ? discount_row.manual_discount : discount_row.disc_;
            row.discount_percentage = discount_value;
        }
    });

    frm.refresh_field("custom_dicount_table");
    frm.refresh_field("items");
}


function apply_brand_discounts(frm) {
    let brand_discounts = {};
    let exceeds_discount = false;

    (frm.doc.custom_dicount_table || []).forEach(row => {
        if (row.brand && row.manual_discount !== undefined) {
            const manualDiscount = safeNumber(row.manual_discount);
            const discDiscount = safeNumber(row.disc_);
            
            if (manualDiscount !== 0) {
                brand_discounts[row.brand] = manualDiscount;
            } else {
                brand_discounts[row.brand] = discDiscount;
            }
        }
        if (safeNumber(row.manual_discount) > safeNumber(row.max_discount)) {
            exceeds_discount = true;
        }
    });

    let items_updated = false;

    (frm.doc.items || []).forEach(item => {
        if (item.brand && brand_discounts[item.brand] !== undefined) {
            let new_discount = brand_discounts[item.brand];
            frappe.model.set_value(item.doctype, item.name, "discount_percentage", new_discount);
            items_updated = true;
        }
    });

    (frm.doc.custom_dicount_table || []).forEach(row => {
        if (row.brand && brand_discounts[row.brand] !== undefined) {
            const discountAmount = safeNumber((safeNumber(row.value) * safeNumber(row.manual_discount)) / 100);
            row.discount_amount = safeFormat(discountAmount);
            row.total_value = safeFormat(safeNumber(row.value) - discountAmount);
        }
    });

    cleanNaNValues(frm);
    frm.refresh_field("items");
    frm.refresh_field("custom_dicount_table");

    if (exceeds_discount) {
        if ("custom_requires_approval_for_discount" in frm.doc) {
            frm.set_value("custom_requires_approval_for_discount", 1);
        } else {
            console.error("Error: Field 'custom_requires_approval' not found in Quotation Doctype!");
        }

        if (frm.doc.custom_requires_approval_for_discount) {
            frm.refresh();
        }
    }
}
// Auto apply discounts when manual discount changes
frappe.ui.form.on('Brand Discount Details', {
    manual_discount: function(frm) {
        apply_brand_discounts(frm);
    },
});



// Modified update_brand_discounts function - Fixed both issues
frappe.ui.form.on("Quotation", {
    update_brand_discounts: function(frm) {
        console.log("1");

        if (!frm.doc.items || frm.doc.items.length === 0) {
            frm.clear_table("custom_dicount_table");
            frm.refresh_field("custom_dicount_table");
            console.log("2");
            return;
        }

        let brand_totals = {};
        let manual_discounts = {};

        // Store existing manual discounts from brand table
        if (frm.doc.custom_dicount_table) {
            frm.doc.custom_dicount_table.forEach(row => {
                manual_discounts[row.brand] = row.manual_discount || 0;
            });
        }

        // Calculate brand totals using CURRENT item discounts (preserve manual changes)
        frm.doc.items.forEach(item => {
            if (item.brand) {
                if (!brand_totals[item.brand]) {
                    brand_totals[item.brand] = {
                        value: 0,
                        total_discount_amount: 0,
                        item_count: 0,
                        manual_discount: manual_discounts[item.brand] || 0
                    };
                }
                
                const itemValue = safeNumber(item.price_list_rate) * safeNumber(item.qty);
                const itemDiscount = safeNumber(item.discount_percentage);
                const discountAmount = (itemValue * itemDiscount) / 100;
                
                brand_totals[item.brand].value += itemValue;
                brand_totals[item.brand].total_discount_amount += discountAmount;
                brand_totals[item.brand].item_count += 1;
            }
        });
        console.log(brand_totals);

        frappe.call({
            method: "erpnext_mxt.custom_functions.brand_discount.get_brand_discounts",
            args: {
                brand_list: Object.keys(brand_totals)
            },
            callback: function(r) {
                if (r.message && Array.isArray(r.message) && r.message.length > 0) {
                    frm.clear_table("custom_dicount_table");
                    console.log("3");

                    r.message.forEach(rule => {
                        if (brand_totals[rule.brand]) {
                            brand_totals[rule.brand].max_discount_percentage = rule.discount_percentage || 0;
                            brand_totals[rule.brand].default_discount_percentage = rule.custom_default_discount_percentage || 0;
                            
                            // Calculate ACTUAL average discount from current items
                            brand_totals[rule.brand].average_discount = 
                                brand_totals[rule.brand].item_count > 0 ? 
                                (brand_totals[rule.brand].total_discount / brand_totals[rule.brand].item_count) : 0;

                            // ISSUE 1 FIX: Use default discount if no items have discounts yet
                            if (brand_totals[rule.brand].average_discount === 0 && brand_totals[rule.brand].manual_discount === 0) {
                                brand_totals[rule.brand].average_discount = brand_totals[rule.brand].default_discount_percentage;
                                
                                // Also apply this default discount to items that don't have any discount
                                frm.doc.items.forEach(item => {
                                    if (item.brand === rule.brand && (item.discount_percentage === 0 || !item.discount_percentage)) {
                                        frappe.model.set_value(item.doctype, item.name, 'discount_percentage', brand_totals[rule.brand].default_discount_percentage);
                                    }
                                });
                            }

                            // Use manual discount if set, otherwise use calculated average
                            let applied_discount = brand_totals[rule.brand].manual_discount > 0 ? 
                                brand_totals[rule.brand].manual_discount : 
                                brand_totals[rule.brand].average_discount;

                            brand_totals[rule.brand].discount_amount =
                                (brand_totals[rule.brand].value * applied_discount) / 100;
                        }
                    });

                    Object.keys(brand_totals).forEach(brand => {
                        let row = frm.add_child("custom_dicount_table");
                        console.log("8");
                        if (row) {
                            row.brand = brand;
                            row.value = brand_totals[brand].value.toFixed(2);
                            row.disc_ = brand_totals[brand].average_discount.toFixed(2);
                            row.discount_amount = brand_totals[brand].discount_amount.toFixed(2);
                            row.total_value = (brand_totals[brand].value - brand_totals[brand].discount_amount).toFixed(2);
                            row.max_discount = brand_totals[brand].max_discount_percentage;
                            
                            // ISSUE 2 FIX: Set manual_discount to match disc_ when it's calculated from item averages
                            if (brand_totals[brand].manual_discount <= 0 && brand_totals[brand].average_discount > 0) {
                                row.manual_discount = brand_totals[brand].average_discount.toFixed(2);
                            } else {
                                row.manual_discount = brand_totals[brand].manual_discount || 0;
                            }
                            
                            console.log(row);
                        }
                    });

                    frm.refresh_field("custom_dicount_table");
                    frm.refresh_field("items"); // Refresh items to show updated discounts
                    console.log("Table Refreshed");
                } else {
                    console.log("Refresh");
                    frm.clear_table("custom_dicount_table");
                    frm.refresh_field("custom_dicount_table");
                }
            }
        });

        frm.refresh();
    }
});

// Function to get brand from Pricing Rule
function setApproval(frm) {
    let requiresApproval = false;
    let brandDiscounts = {};
    console.log("4")

    // Collect unique brands from the items in the form
    let brandList = [...new Set((frm.doc.items || []).map(item => item.brand).filter(brand => brand))];

    if (brandList.length === 0) {
        frm.set_value("custom_requires_approval_for_discount", 0);
        return;
    }

    // Call the server-side function to get brand discounts
    frappe.call({
        method: "erpnext_mxt.custom_functions.brand_discount.get_brand_discounts",
        args: {
            brand_list: brandList // Pass as an array instead of JSON.stringify
        },
        async: false, // Synchronous execution (consider avoiding this in production)
        callback: function(response) {
            if (response.message) {
                console.log("5")
                // Map brand discounts
                response.message.forEach(discount => {
                    if (discount.brand) {
                        brandDiscounts[discount.brand] = discount.discount_percentage || 0;
                    }
                    if (discount.custom_default_discount_percentage) {
                        brandDiscounts[discount.min_brand] = discount.custom_default_discount_percentage || 0;
                    }
                });
                

                // Iterate over items and check discount limits
                (frm.doc.items || []).forEach(item => {
                    if (item.item_code && item.brand) {
                        let itemDiscount = item.discount_percentage || 0;
                        let maxAllowedDiscount = brandDiscounts[item.brand] || 0;
                        let minAllowedDiscount = brandDiscounts[item.min_brand] || 0;

                        if (itemDiscount > maxAllowedDiscount || itemDiscount < minAllowedDiscount) {
                            requiresApproval = true;
                            // frappe.show_alert({
                            //     message: Item ${item.item_code} needs discount approval,
                            //     indicator: 'orange'
                            // }, 5);

                        }
                    }
                });

                // *Set Approval Flag*
                frm.set_value("custom_requires_approval_for_discount", requiresApproval ? 1 : 0);
            } else {
                frm.set_value("custom_requires_approval_for_discount", 0);
            }
        }
    });
}




// Fetch brand separately for each Pricing Rule
function setApplyDiscount(frm) {
    let brandDiscountMap = {};

    // Calculate weighted average discount per brand from current item values
    (frm.doc.items || []).forEach(row => {
        if (row.brand) {
            if (!brandDiscountMap[row.brand]) {
                brandDiscountMap[row.brand] = {
                    total_discount_amount: 0,
                    total_value: 0
                };
            }
            const itemValue = safeNumber(row.price_list_rate) * safeNumber(row.qty);
            const discountAmount = (itemValue * safeNumber(row.discount_percentage)) / 100;
            
            brandDiscountMap[row.brand].total_discount_amount += discountAmount;
            brandDiscountMap[row.brand].total_value += itemValue;
        }
    });
    
    // Compute the weighted average discount for each brand - PREVENT NaN
    Object.keys(brandDiscountMap).forEach(brand => {
        brandDiscountMap[brand].average_discount = brandDiscountMap[brand].total_value > 0 ?
            safeNumber((brandDiscountMap[brand].total_discount_amount / brandDiscountMap[brand].total_value) * 100) : 0;
    });

    // Update the custom_discount_table with the computed average discounts
    (frm.doc.custom_dicount_table || []).forEach(row => {
        if (brandDiscountMap[row.brand]) {
            row.disc_ = safeFormat(brandDiscountMap[row.brand].average_discount);
            row.applied_discount = safeFormat(brandDiscountMap[row.brand].average_discount);
            
            // Update manual_discount to match the calculated average
            if (safeNumber(row.manual_discount) <= 0) {
                row.manual_discount = safeFormat(brandDiscountMap[row.brand].average_discount);
            }
        }
    });

    // Clean any remaining NaN values
    cleanNaNValues(frm);
    
    frm.refresh_field('custom_dicount_table');
    frm.refresh();
}


// UPDATED: Clean NaN values function
function cleanNaNValues(frm) {
    (frm.doc.custom_dicount_table || []).forEach(row => {
        row.value = safeFormat(row.value || 0);
        row.disc_ = safeFormat(row.disc_ || 0);
        row.applied_discount = safeFormat(row.applied_discount || 0);
        row.manual_discount = safeFormat(row.manual_discount || 0);
        row.discount_amount = safeFormat(row.discount_amount || 0);
        row.total_value = safeFormat(row.total_value || 0);
        row.max_discount = safeFormat(row.max_discount || 0);
    });
}

// Auto-update function that also syncs manual_discount
function updateBrandAveragesOnly(frm) {
    let brandDiscountMap = {};

    (frm.doc.items || []).forEach(row => {
        if (row.brand) {
            if (!brandDiscountMap[row.brand]) {
                brandDiscountMap[row.brand] = {
                    total_discount_amount: 0,
                    total_value: 0
                };
            }
            const itemValue = safeNumber(row.price_list_rate) * safeNumber(row.qty);
            const discountAmount = (itemValue * safeNumber(row.discount_percentage)) / 100;
            
            brandDiscountMap[row.brand].total_discount_amount += discountAmount;
            brandDiscountMap[row.brand].total_value += itemValue;
        }
    });
    
    Object.keys(brandDiscountMap).forEach(brand => {
        brandDiscountMap[brand].average_discount = brandDiscountMap[brand].total_value > 0 ?
            safeNumber((brandDiscountMap[brand].total_discount_amount / brandDiscountMap[brand].total_value) * 100) : 0;
    });

    (frm.doc.custom_dicount_table || []).forEach(row => {
        if (brandDiscountMap[row.brand]) {
            row.applied_discount = safeFormat(brandDiscountMap[row.brand].average_discount);
            row.disc_ = safeFormat(brandDiscountMap[row.brand].average_discount);
            row.manual_discount = safeFormat(brandDiscountMap[row.brand].average_discount);
            
            const discount_amount = safeNumber((brandDiscountMap[row.brand].total_value * brandDiscountMap[row.brand].average_discount) / 100);
            row.discount_amount = safeFormat(discount_amount);
            row.total_value = safeFormat(brandDiscountMap[row.brand].total_value - discount_amount);
        }
    });

    cleanNaNValues(frm);
    frm.refresh_field('custom_dicount_table');
}



function update_brand_discounts_for_save(frm) {
    if (!frm.doc.items || frm.doc.items.length === 0) {
        frm.clear_table("custom_dicount_table");
        return;
    }

    const brand_totals = {};
    const manual_discounts = {};

    // Get manual discounts
    (frm.doc.custom_dicount_table || []).forEach(row => {
        manual_discounts[row.brand] = safeNumber(row.manual_discount);
    });

    // Compute brand totals
    (frm.doc.items || []).forEach(item => {
        if (!item.brand) return;

        if (!brand_totals[item.brand]) {
            brand_totals[item.brand] = {
                value: 0,
                total_discount: 0,
                item_count: 0,
                manual_discount: manual_discounts[item.brand] || 0
            };
        }

        const itemValue = safeNumber(item.price_list_rate) * safeNumber(item.qty);
        const itemDiscount = safeNumber(item.discount_percentage);
        
        brand_totals[item.brand].value += itemValue;
        brand_totals[item.brand].total_discount += itemDiscount;
        brand_totals[item.brand].item_count += 1;
    });

    // Calculate averages and update table
    frm.clear_table("custom_dicount_table");
    Object.keys(brand_totals).forEach(brand => {
        const brandData = brand_totals[brand];
        
        // Calculate average discount - PREVENT NaN
        const average_discount = brandData.item_count > 0 ? 
            safeNumber(brandData.total_discount / brandData.item_count) : 0;
        
        const applied_discount = brandData.manual_discount > 0 ? brandData.manual_discount : average_discount;
        const discount_amount = safeNumber((brandData.value * applied_discount) / 100);
        const total_value = safeNumber(brandData.value - discount_amount);

        let row = frm.add_child("custom_dicount_table", {
            brand: brand,
            value: safeFormat(brandData.value),
            disc_: safeFormat(average_discount),
            applied_discount: safeFormat(average_discount),
            manual_discount: safeFormat(brandData.manual_discount > 0 ? brandData.manual_discount : average_discount),
            discount_amount: safeFormat(discount_amount),
            total_value: safeFormat(total_value),
            max_discount: safeFormat(brandDiscounts[brand] || 0)
        });
    });

    // Update items' discount percentages
    // (frm.doc.items || []).forEach(row => {
    //     const discount_row = frm.doc.custom_dicount_table.find(d => d.brand === row.brand);
    //     if (discount_row) {
    //         const discount_value = safeNumber(discount_row.manual_discount) > 0 ? 
    //             safeNumber(discount_row.manual_discount) : safeNumber(discount_row.disc_);
    //         row.discount_percentage = discount_value;
    //     }
    // });

    // frm.refresh_field("custom_dicount_table");
    // frm.refresh_field("items");
}

// Keep the auto-update event handler
// Auto-update event handler
frappe.ui.form.on('Quotation Item', {
    discount_percentage: function(frm, cdt, cdn) {
        updateBrandAveragesOnly(frm);
    }
});

frappe.ui.form.on('Brand Discount Details', {
    manual_discount: function(frm) {
        // Clean and apply discounts when manual discount changes
        cleanNaNValues(frm);
        apply_brand_discounts(frm);
    },
});