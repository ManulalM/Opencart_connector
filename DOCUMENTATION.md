# OpenCart-Odoo Bridge - Complete Documentation

A beginner-friendly guide explaining every file, every function, and why it exists.

---

## Table of Contents

1. [What This Module Does](#what-this-module-does)
2. [How Odoo Modules Work (Basics)](#how-odoo-modules-work-basics)
3. [Module Structure](#module-structure)
4. [File-by-File Explanation](#file-by-file-explanation)
   - [__manifest__.py](#__manifest__py)
   - [__init__.py](#__init__py)
   - [models/__init__.py](#models__init__py)
   - [models/opencart_config.py](#modelsopencart_configpy)
   - [models/product_sync.py](#modelsproduct_syncpy)
   - [models/customer_sync.py](#modelscustomer_syncpy)
   - [models/order_sync.py](#modelsorder_syncpy)
   - [models/stock_sync.py](#modelsstock_syncpy)
   - [security/ir.model.access.csv](#securityirmodelaccesscsv)
   - [views/ (XML files)](#views-xml-files)
   - [data/cron.xml](#datacronxml)
5. [Data Flow Diagrams](#data-flow-diagrams)
6. [Key Odoo Concepts Used](#key-odoo-concepts-used)
7. [Key Python Concepts Used](#key-python-concepts-used)
8. [OpenCart Database Tables Used](#opencart-database-tables-used)
9. [Troubleshooting](#troubleshooting)

---

## What This Module Does

This module connects **Odoo 18** to an **OpenCart** e-commerce store by directly reading/writing to OpenCart's MySQL database.

It performs 4 types of sync:

| Sync | Direction | What it does |
|------|-----------|--------------|
| Product Sync | Odoo --> OpenCart | Pushes Odoo products (name, price, SKU, stock) into OpenCart's database |
| Customer Sync | OpenCart --> Odoo | Pulls OpenCart customers into Odoo as contacts (res.partner) |
| Order Sync | OpenCart --> Odoo | Pulls OpenCart orders into Odoo as sale orders |
| Stock Sync | Odoo --> OpenCart | Updates product quantities in OpenCart to match Odoo's stock levels |

**Why direct MySQL instead of API?**
OpenCart's REST API is limited - it doesn't expose all product fields, can't bulk-create, and is slow. Direct MySQL gives full control and is much faster.

---

## How Odoo Modules Work (Basics)

If you're new to Odoo, here's how a custom module is structured:

- **`__manifest__.py`** - Tells Odoo about the module (name, dependencies, which files to load)
- **`__init__.py`** - Python entry point that imports your code
- **`models/`** - Python classes that define database tables and business logic
- **`views/`** - XML files that define what users see in the browser (forms, lists, menus)
- **`security/`** - Who can read/write/create/delete records
- **`data/`** - Default data loaded when the module is installed (like cron jobs)

Every model (Python class) in Odoo automatically creates a database table. For example, `_name = 'opencart.config'` creates a table called `opencart_config` in Odoo's PostgreSQL database.

---

## Module Structure

```
opencart_connector/
|-- __manifest__.py          # Module metadata and file list
|-- __init__.py              # Root Python import
|-- models/
|   |-- __init__.py          # Imports all model files
|   |-- opencart_config.py   # MySQL connection settings + manual sync buttons
|   |-- product_sync.py      # Odoo --> OpenCart product push logic
|   |-- customer_sync.py     # OpenCart --> Odoo customer pull logic
|   |-- order_sync.py        # OpenCart --> Odoo order pull logic
|   |-- stock_sync.py        # Odoo --> OpenCart stock quantity push
|-- views/
|   |-- opencart_config_view.xml   # Config form + list view
|   |-- product_sync_view.xml      # Product sync list view
|   |-- customer_sync_view.xml     # Customer sync list view
|   |-- order_sync_view.xml        # Order sync list view
|   |-- menuitems.xml              # Left sidebar menu structure
|-- security/
|   |-- ir.model.access.csv        # Access rights for all models
|-- data/
|   |-- cron.xml                   # Scheduled automatic sync jobs
```

---

## File-by-File Explanation

### __manifest__.py

```python
{
    'name': 'Opencart-Odoo-Bridge',
    'version': '18.0.1.0.0',
    'depends': ['sale', 'stock', 'product'],
    'data': [
        'security/ir.model.access.csv',
        'views/opencart_config_view.xml',
        ...
    ],
}
```

**Why does this file exist?**
Every Odoo module MUST have a `__manifest__.py`. It's the module's identity card.

- **`name`** - What appears in Odoo's Apps list
- **`version`** - `18.0.1.0.0` means: Odoo 18, version 1.0.0 of the module
- **`depends`** - Other modules that must be installed first. We need:
  - `sale` - because we create sale.order records
  - `stock` - because we read stock quantities (qty_available)
  - `product` - because we read product.template records
- **`data`** - List of XML/CSV files to load, **order matters!** Security must come before views, views before menus

---

### __init__.py

```python
from . import models
```

**Why?** Python needs this file to recognize the folder as a package. It imports the `models` subfolder so Odoo can find your model classes.

---

### models/__init__.py

```python
from . import opencart_config
from . import product_sync
from . import customer_sync
from . import order_sync
from . import stock_sync
```

**Why?** Each line tells Python to load that file. If you create a new model file but forget to add it here, Odoo won't know it exists and you'll get errors.

---

### models/opencart_config.py

This is the **central configuration** model. It stores MySQL connection details and provides manual sync buttons.

#### The Fields (Database Columns)

```python
class OpencartConfig(models.Model):
    _name = 'opencart.config'          # Creates table "opencart_config" in Odoo's database
    _description = 'Opencart Connector'
    _rec_name = 'name'                 # Which field to show when referencing this record
```

- **`_name`** - The unique identifier for this model. Used everywhere to reference it (in XML, in Python via `self.env['opencart.config']`)
- **`models.Model`** - This is a "persistent" model, meaning data is saved permanently in the database

```python
    name = fields.Char(...)           # A text field for the config name
    url = fields.Char(...)            # The OpenCart store URL
    active = fields.Boolean(...)      # If False, this config is ignored
    db_host = fields.Char(...)        # MySQL server hostname
    db_port = fields.Integer(...)     # MySQL port (default 3306)
    db_user = fields.Char(...)        # MySQL username
    db_password = fields.Char(...)    # MySQL password
    db_name = fields.Char(...)        # MySQL database name
    db_table_prefix = fields.Char(...)# OpenCart table prefix (default "oc_")
```

**Why `db_table_prefix`?** OpenCart lets you customize table prefixes during installation. Most use `oc_` but some might use `opencart_` or something else. Our SQL queries use this prefix so they work with any setup.

#### The Methods (Functions)

**`_get_active_config(cls, env)`**
```python
@classmethod
def _get_active_config(cls, env):
    config = env['opencart.config'].search([('active', '=', True)], limit=1)
```
- Finds the first config record where `active = True`
- **Why `@classmethod`?** So it can be called without a specific record: `OpencartConfig._get_active_config(self.env)`
- **Why `limit=1`?** We only need one config. If you have multiple, only the first active one is used

**`get_mysql_connection(self)`**
```python
def get_mysql_connection(self):
    import mysql.connector
    return mysql.connector.connect(
        host=self.db_host,
        port=self.db_port,
        user=self.db_user,
        password=self.db_password,
        database=self.db_name,
    )
```
- Creates and returns a MySQL database connection using the stored credentials
- **Why `import` inside the function?** `mysql.connector` is an external library. Importing at the top level would crash Odoo if it's not installed. Importing inside the function means the error only happens when you actually try to connect
- **Why return the connection?** The caller (sync methods) needs the connection to run SQL queries, and is responsible for closing it when done

**`action_test_mysql(self)`**
```python
def action_test_mysql(self):
    self.ensure_one()  # Make sure we're working with exactly ONE record
    conn = self.get_mysql_connection()
    cursor = conn.cursor()
    cursor.execute(f'SELECT COUNT(*) FROM {self.db_table_prefix}product')
    count = cursor.fetchone()[0]
```
- **Why does this exist?** So you can verify your MySQL credentials are correct BEFORE running a sync
- **`self.ensure_one()`** - Safety check. Odoo buttons can sometimes be called on multiple records. This throws an error if that happens
- It runs a simple `SELECT COUNT(*)` query to verify the connection works
- Returns a notification dict that Odoo displays as a green popup message

**Manual Sync Buttons** (`action_sync_products`, `action_sync_customers`, etc.)
```python
def action_sync_products(self):
    self.ensure_one()
    self.env['opencart.product.sync']._cron_sync_products()
    return self._notify('Product sync completed.')
```
- **Why do these exist?** So you can trigger a sync immediately from the UI instead of waiting for the cron job
- **`self.env['opencart.product.sync']`** - This is how you access another model in Odoo. `self.env` is a dictionary of all models
- Each button simply calls the same method that the cron job calls

**`action_sync_all(self)`**
```python
def action_sync_all(self):
    self.env['opencart.customer.sync']._cron_sync_customers()   # 1st
    self.env['opencart.product.sync']._cron_sync_products()     # 2nd
    self.env['opencart.order.sync']._cron_sync_orders()         # 3rd
    self.env['opencart.stock.sync']._cron_sync_stock()          # 4th
```
- **Why this order?** Dependencies:
  1. Customers first - because orders need customer records to exist
  2. Products second - because orders try to match products by SKU
  3. Orders third - now customers and products are ready
  4. Stock last - needs product mappings to know which OC products to update

**`_notify(self, message)`**
- Helper method to return a green popup notification
- **Why `_` prefix?** In Odoo convention, methods starting with `_` are "private" - they don't appear as available actions in the UI. Only methods without `_` can be used as button actions

---

### models/product_sync.py

This model pushes Odoo products INTO OpenCart's MySQL database.

#### The Fields

```python
odoo_product_id = fields.Many2one('product.template', ...)  # Link to Odoo product
opencart_product_id = fields.Integer(...)                    # The product_id in OpenCart's DB
last_sync = fields.Datetime(...)                             # When was this last synced
sync_status = fields.Selection([...])                        # 'success' or 'failed'
sync_message = fields.Text(...)                              # Human-readable status message
```

- **`Many2one`** means: each sync record points to ONE Odoo product. It's like a foreign key in SQL
- **Why store `opencart_product_id`?** This is the **mapping**. It remembers "Odoo product #5 = OpenCart product #12". Without this, we'd create duplicates every time we sync

#### The Main Sync Method: `_cron_sync_products(self)`

This is the heart of product sync. Here's what it does step by step:

```python
config = self._get_config()                    # Step 1: Get MySQL credentials
prefix = config.db_table_prefix or 'oc_'       # Step 2: Get table prefix
products = self.env['product.template'].search( # Step 3: Get all sellable Odoo products
    [('sale_ok', '=', True)]
)
conn = config.get_mysql_connection()            # Step 4: Connect to MySQL
cursor = conn.cursor(dictionary=True)           # Step 5: Create cursor (dictionary=True means
                                                #         results come as dicts, not tuples)
```

Then for each product:
```python
existing = self.search([('odoo_product_id', '=', product.id)], limit=1)
```
- **Check if we've synced this product before** by looking for an existing mapping record
- If mapping exists AND has an OpenCart ID --> **UPDATE** the existing OpenCart product
- If no mapping exists --> **INSERT** a new product into OpenCart

**Why `conn.commit()` at the end?**
MySQL doesn't auto-save changes. Without `commit()`, all your INSERTs and UPDATEs would be lost when the connection closes.

**Why `try/finally` with `cursor.close()` and `conn.close()`?**
Even if an error occurs, we MUST close the MySQL connection. Otherwise, we'd leak connections and eventually MySQL would refuse new ones.

#### `_insert_oc_product(self, cursor, prefix, product)`

Creates a NEW product in OpenCart. It inserts into 3 tables:

1. **`oc_product`** - The main product record (SKU, price, weight, quantity, status)
2. **`oc_product_description`** - The product's name and description (OpenCart separates these for multi-language support)
3. **`oc_product_to_store`** - Which store(s) the product belongs to (OpenCart supports multi-store; store 0 = default)

**Why so many columns in the INSERT?**
OpenCart's `oc_product` table has 30+ columns with `NOT NULL` and no default values. If we don't provide them all, MySQL throws an error like the "Field 'upc' doesn't have a default value" error we fixed.

**Why `cursor.lastrowid`?**
After an INSERT, this gives us the auto-generated `product_id`. We need it to insert into `oc_product_description` and to store in our mapping.

#### `_update_oc_product(self, cursor, prefix, oc_id, product)`

Updates an EXISTING OpenCart product. Only modifies the fields we care about (name, price, SKU, weight, quantity).

**Why is UPDATE simpler than INSERT?**
We only need to change specific columns. The other columns (like `upc`, `ean`, `isbn`) keep their existing values.

---

### models/customer_sync.py

This model pulls OpenCart customers INTO Odoo as `res.partner` records.

#### The Main Sync Method: `_cron_sync_customers(self)`

```python
synced = self.search([]).mapped('opencart_customer_id')
synced_ids = tuple(synced) if synced else (0,)
```
- **Get all already-synced customer IDs** so we can skip them
- **Why `(0,)` as fallback?** SQL `NOT IN ()` with an empty tuple is invalid syntax. Using `(0,)` means "not in (0)" which matches nothing (no customer has ID 0)

```python
cursor.execute(f"""
    SELECT c.customer_id, c.firstname, c.lastname, c.email, c.telephone,
           a.address_1, a.address_2, a.city, a.postcode, a.country_id as oc_country_id
    FROM {prefix}customer c
    LEFT JOIN {prefix}address a ON a.customer_id = c.customer_id
        AND a.address_id = c.address_id
    WHERE c.customer_id NOT IN (...)
""")
```
- **Why LEFT JOIN with address?** A customer might not have an address yet. `LEFT JOIN` means: get the customer even if they have no address (address fields will be NULL)
- **Why `a.address_id = c.address_id`?** OpenCart stores the customer's "default address" ID. We only want that one, not all their addresses

**Country mapping:**
```python
cursor.execute(f"SELECT iso_code_2 FROM {prefix}country WHERE country_id = %s")
country = self.env['res.country'].search([('code', '=', row['iso_code_2'])])
```
- OpenCart stores countries by numeric ID (e.g., 100 = India)
- Odoo stores countries by ISO code (e.g., "IN" = India)
- We look up the ISO code from OpenCart's `oc_country` table, then find the matching Odoo country

**`customer_rank = 1`** - This tells Odoo this partner is a customer (not a vendor). It affects which filters show them.

---

### models/order_sync.py

This model pulls OpenCart orders INTO Odoo as `sale.order` records.

#### The Main Sync Method: `_cron_sync_orders(self)`

```python
WHERE order_id NOT IN (...) AND order_status_id > 0
```
- **Why `order_status_id > 0`?** In OpenCart, `order_status_id = 0` means the order is incomplete (customer abandoned checkout). We only want real, confirmed orders.

For each order:
1. Find or create a customer (`_get_or_create_partner`)
2. Get the order's line items (`_get_order_lines`)
3. Create a `sale.order` in Odoo

```python
'origin': f"OC-{oc_order['order_id']}",
```
- **Why `origin`?** This field in Odoo shows where the order came from. "OC-42" means "OpenCart order #42". Makes it easy to trace orders back.

#### `_get_or_create_partner(self, oc_order)`

This tries 3 strategies to find the right customer, in order:

1. **Check customer sync mapping** - If we previously synced this customer, use that partner
2. **Search by email** - Maybe the customer exists in Odoo from another source
3. **Create new** - If nothing found, create a new partner from the order data

**Why this priority order?** The mapping is most reliable (exact match). Email search is a good fallback. Creating new is the last resort.

#### `_get_order_lines(self, cursor, prefix, oc_order_id)`

```python
cursor.execute(f"SELECT name, model, quantity, price FROM {prefix}order_product WHERE order_id = %s")
```
- Fetches the items in the order from OpenCart
- **`model`** in OpenCart = SKU in Odoo (`default_code`). We try to match them

```python
lines.append((0, 0, {...}))
```
- **Why `(0, 0, {...})`?** This is Odoo's special syntax for creating related records. It means "create a new line with these values". The format is `(command, id, values)` where command `0` = create.

---

### models/stock_sync.py

This model pushes Odoo stock quantities TO OpenCart.

```python
class StockSync(models.TransientModel):
```

**Why `TransientModel` instead of `Model`?**
- `Model` = permanent database table (records stay forever)
- `TransientModel` = temporary records, auto-deleted after some time
- Stock sync doesn't need to store its own data. It reads mappings from `product_sync` and updates OpenCart. No need to keep records around.

#### The Main Sync Method: `_cron_sync_stock(self)`

```python
mappings = self.env['opencart.product.sync'].search([
    ('opencart_product_id', '>', 0),
    ('odoo_product_id', '!=', False),
])
```
- Gets all product mappings that have BOTH an Odoo product AND an OpenCart product ID
- **Why check both?** A mapping might exist with `sync_status = 'failed'` and no OpenCart ID. We can't update a product that doesn't exist in OpenCart.

```python
qty = product.qty_available or 0
cursor.execute(f"UPDATE {prefix}product SET quantity = %s WHERE product_id = %s")
```
- **`qty_available`** = the "On Hand" quantity in Odoo's inventory
- We directly update OpenCart's product quantity to match

---

### security/ir.model.access.csv

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_opencart_config,opencart.config,model_opencart_config,base.group_user,1,1,1,1
```

**Why does this file exist?**
Odoo's security model blocks ALL access by default. Without this file, no one could see or use your models. Each line grants permissions:

- **`model_id:id`** - Which model (table) this rule applies to. `model_opencart_config` refers to the `opencart.config` model (Odoo auto-generates this ID by replacing dots with underscores)
- **`group_id:id`** - Which user group gets access. `base.group_user` = all internal users
- **`perm_read,perm_write,perm_create,perm_unlink`** - 1=allowed, 0=denied. Read/Write/Create/Delete

---

### Views (XML Files)

Views tell Odoo HOW to display your data in the browser.

#### opencart_config_view.xml

Contains 3 things:

**1. Form View** - What you see when you click on a config record
```xml
<form string="OpenCart Configuration">
    <header>
        <button name="action_test_mysql" string="Test MySQL Connection"
                type="object" class="btn-primary"/>
    </header>
```
- **`<header>`** - The blue bar at the top with action buttons
- **`type="object"`** - Means clicking this button calls a Python method with that name on the current record
- **`class="btn-primary"`** - Blue button. `btn-secondary` = grey button

**2. List View** - What you see in the table/list of all configs
```xml
<list string="OpenCart Configurations">
    <field name="name"/>
    <field name="url"/>
    <field name="active"/>
</list>
```

**3. Action** - Connects the view to a menu item
```xml
<record id="action_opencart_config" model="ir.actions.act_window">
    <field name="res_model">opencart.config</field>
    <field name="view_mode">list,form</field>
</record>
```
- **`ir.actions.act_window`** - "Open a window showing this model"
- **`view_mode`** - "Show list view first, form view when they click a record"

#### Sync View Files (product_sync_view.xml, etc.)

All follow the same pattern:
```xml
<field name="sync_status"
       decoration-success="sync_status == 'success'"
       decoration-danger="sync_status == 'failed'"
       widget="badge"/>
```
- **`widget="badge"`** - Shows the value as a colored badge/tag
- **`decoration-success`** - Green when status is "success"
- **`decoration-danger`** - Red when status is "failed"

#### menuitems.xml

```xml
<menuitem id="menu_opencart_root" name="OpenCart" sequence="80"/>
<menuitem id="menu_opencart_config" name="Configuration"
          parent="menu_opencart_root" action="action_opencart_config"/>
```
- **`sequence="80"`** - Controls the menu's position in the sidebar (lower = higher up)
- **`parent`** - Creates a submenu under the specified parent
- **`action`** - Which action to trigger when clicked (opens the corresponding view)

---

### data/cron.xml

```xml
<record id="cron_sync_products" model="ir.cron">
    <field name="name">OpenCart: Sync Products</field>
    <field name="model_id" ref="model_opencart_product_sync"/>
    <field name="state">code</field>
    <field name="code">model._cron_sync_products()</field>
    <field name="interval_number">30</field>
    <field name="interval_type">minutes</field>
    <field name="active">True</field>
</record>
```

**Why does this file exist?**
Cron jobs = scheduled tasks that run automatically. Without these, syncing would only happen when you click buttons manually.

- **`ir.cron`** - Odoo's built-in model for scheduled actions
- **`model_id`** - Which model to call the method on
- **`code`** - The Python code to execute. `model` is a magic variable that refers to the model
- **`interval_number` + `interval_type`** - "Run every 30 minutes"
- **`active`** - Set to False to disable the cron without deleting it

**Cron intervals in this module:**
| Cron | Interval | Why |
|------|----------|-----|
| Customer Sync | 15 min | New customers appear moderately often |
| Product Sync | 30 min | Products don't change very frequently |
| Order Sync | 10 min | Orders are time-sensitive, sync them fast |
| Stock Sync | 15 min | Stock changes with each order/receipt |

You can change these intervals in **Settings > Technical > Scheduled Actions**.

---

## Data Flow Diagrams

### Product Sync (Odoo --> OpenCart)

```
Odoo product.template              OpenCart MySQL
+------------------+               +------------------+
| name: "T-Shirt"  |  -- INSERT -> | oc_product       |
| list_price: 29.99|               | product_id: 42   |
| default_code: TSH|               | price: 29.99     |
| qty_available: 50|               | model: TSH       |
+------------------+               +------------------+
                                   | oc_product_description
                                   | name: "T-Shirt"  |
                                   +------------------+
                                   | oc_product_to_store
                                   | store_id: 0      |
                                   +------------------+

Mapping Record (in Odoo):
+------------------------------------------+
| odoo_product_id: 5 (T-Shirt)             |
| opencart_product_id: 42                  |
| sync_status: success                     |
+------------------------------------------+
```

### Customer Sync (OpenCart --> Odoo)

```
OpenCart MySQL                     Odoo res.partner
+------------------+               +------------------+
| oc_customer      |  -- CREATE -> | name: "John Doe" |
| customer_id: 10  |               | email: john@...  |
| firstname: John  |               | phone: 555-1234  |
| lastname: Doe    |               | customer_rank: 1 |
| email: john@...  |               +------------------+
+------------------+
```

### Order Sync (OpenCart --> Odoo)

```
OpenCart MySQL                     Odoo sale.order
+------------------+               +--------------------+
| oc_order         |  -- CREATE -> | partner_id: John   |
| order_id: 100    |               | origin: "OC-100"   |
| customer_id: 10  |               | date_order: ...    |
+------------------+               +--------------------+
| oc_order_product  |               | sale.order.line    |
| name: "T-Shirt"  |  -- CREATE -> | product: T-Shirt   |
| quantity: 2       |               | qty: 2             |
| price: 29.99      |               | price_unit: 29.99  |
+------------------+               +--------------------+
```

### Stock Sync (Odoo --> OpenCart)

```
Odoo product.template              OpenCart MySQL
+------------------+               +------------------+
| qty_available: 48|  -- UPDATE -> | oc_product       |
+------------------+               | quantity: 48     |
                                   +------------------+
(Uses the mapping from Product Sync to know which OC product to update)
```

---

## Key Odoo Concepts Used

### `self.env`
A dictionary-like object that gives access to all Odoo models. Example:
```python
self.env['sale.order']          # Access the sale order model
self.env['res.partner'].create({...})  # Create a new contact
```

### `self.search([domain])`
Find records matching conditions. The domain is a list of tuples:
```python
self.search([('active', '=', True)])              # WHERE active = True
self.search([('sale_ok', '=', True)], limit=1)    # LIMIT 1
```

### `self.create({values})`
Create a new record in the database.

### `record.write({values})`
Update an existing record.

### `fields.Many2one('other.model')`
A foreign key relationship. "This record points to one record in another table."

### `(0, 0, {values})` syntax
Used when creating child records inline. For example, creating order lines when creating an order:
```python
'order_line': [(0, 0, {'product_id': 1, 'quantity': 5})]
```
The `0` command means "create". Other commands: `1` = update, `2` = delete, `4` = link existing.

### `self.ensure_one()`
Verifies you're working with exactly one record. Prevents bugs where a button accidentally runs on multiple records.

---

## Key Python Concepts Used

### `_logger`
```python
import logging
_logger = logging.getLogger(__name__)
_logger.info('Sync completed')
_logger.error('Something went wrong: %s', error)
```
Writes messages to Odoo's server log. Essential for debugging cron jobs (which run silently in the background).

### `try/except/finally`
```python
try:
    # Do risky stuff (MySQL queries)
except Exception as e:
    # Handle errors (log them, mark as failed)
finally:
    # ALWAYS runs, even if there was an error
    cursor.close()
    conn.close()
```

### f-strings
```python
f"OC-{order_id}"           # "OC-42"
f"Connected! {count} products"
```
Python's way to embed variables in strings.

### `dictionary=True` in MySQL cursor
```python
cursor = conn.cursor(dictionary=True)
```
Without it: `cursor.fetchone()` returns `(1, 'John', 'Doe')`
With it: `cursor.fetchone()` returns `{'customer_id': 1, 'firstname': 'John', 'lastname': 'Doe'}`
Much easier to work with!

---

## OpenCart Database Tables Used

| Table | Used By | Purpose |
|-------|---------|---------|
| `oc_product` | Product Sync, Stock Sync | Main product data (price, SKU, qty) |
| `oc_product_description` | Product Sync | Product name, description (multi-language) |
| `oc_product_to_store` | Product Sync | Which store a product belongs to |
| `oc_customer` | Customer Sync | Customer accounts |
| `oc_address` | Customer Sync | Customer addresses |
| `oc_country` | Customer Sync | Country lookup (ID to ISO code) |
| `oc_order` | Order Sync | Order header (customer, total, date) |
| `oc_order_product` | Order Sync | Order line items (products, qty, price) |

---

## Troubleshooting

### "No active OpenCart configuration found"
Create a config record in OpenCart > Configuration and make sure Active is checked.

### "MySQL connection failed"
- Check that MySQL is running: `sudo systemctl status mysql`
- Verify credentials match OpenCart's `config.php`
- Make sure Odoo's server can reach the MySQL host (localhost vs remote)

### "Field 'xxx' doesn't have a default value"
OpenCart's tables have many NOT NULL columns. The INSERT query needs to include ALL of them. Check the column with `DESCRIBE oc_table_name;` and add it to the INSERT.

### Products sync but don't appear in OpenCart
Make sure `oc_product_to_store` has an entry. Without it, OpenCart won't show the product in any store.

### Orders import but customer is "OpenCart Customer"
The customer sync should run BEFORE order sync. Run "Sync All" which does them in the correct order.

### Duplicate products after re-sync
Check the `opencart.product.sync` mapping records. If a mapping was deleted, the module won't know the product already exists in OpenCart and will create it again.
