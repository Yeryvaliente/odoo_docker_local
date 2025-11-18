=======================
Twonary POS Category Notes
=======================

This module extends the Point of Sale functionality to allow making customer notes and internal notes required based on product categories.

Features
========

* Add "Customer Note Required" and "Internal Note Required" checkboxes to POS categories
* Only one type of note can be required per category (mutually exclusive)
* **Hierarchical inheritance**: If a category doesn't have note requirements, it will check parent categories up the hierarchy
* When adding a product from a category with required notes to the cart, a popup will appear asking for the required note
* Supports both customer notes and internal notes with predefined options for internal notes

Configuration
=============

1. Go to Point of Sale > Configuration > PoS Product Categories
2. Edit or create a category
3. In the "Note Requirements" section, check either:
   - "Require Customer Note" - for customer-facing notes
   - "Require Internal Note" - for internal/kitchen notes
4. Save the category

Usage
=====

When a product from a category with required notes is added to the cart in the POS:

1. The system checks the product's categories for note requirements
2. If no requirements are found, it checks parent categories up the hierarchy
3. A popup will appear asking for the required note (from the category that has the requirement)
4. For customer notes: a simple text input
5. For internal notes: predefined note buttons plus text input
6. The note must be provided to add the product to the cart
7. The note will be saved with the order line

**Hierarchy Example:**
- Parent Category: "Food" (Customer Note Required = True)
- Child Category: "Beverages" (No requirements set)
- Product in "Beverages" → Will require customer note from "Food" parent category

Technical Notes
===============

* The module patches the `addLineToCurrentOrder` method in POS
* Notes are stored in the `customer_note` field of order lines
* The module follows Odoo 18 conventions and best practices

Author
======

Twonary
https://twonary.com
