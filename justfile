# Bilka To Go CLI

# Sog efter varer
search query *args:
    uv run bilka_cli.py search "{{query}}" {{args}}

# Vis detaljer for en vare
details product_id:
    uv run bilka_cli.py details {{product_id}}

# Vis kurven
basket:
    uv run bilka_cli.py basket

# Laeg en vare i kurven
add product_id quantity="1":
    uv run bilka_cli.py add {{product_id}} {{quantity}}

# Fjern en vare fra kurven
remove product_id *quantity:
    uv run bilka_cli.py remove {{product_id}} {{quantity}}

# Laeg en indkoebsliste i kurven, fx: just shop "letmaelk:2" "rugbroed"
shop *items:
    uv run bilka_cli.py shop {{items}}

# Se hvad en indkoebsliste ville laegge i kurven
plan *items:
    uv run bilka_cli.py shop --dry-run {{items}}

# Tom kurven
empty:
    uv run bilka_cli.py empty --yes

# Ordrehistorik
history limit="10":
    uv run bilka_cli.py history -n {{limit}}

# Kopier en tidligere ordre ind i kurven
reorder order_id:
    uv run bilka_cli.py reorder {{order_id}}

# Ledige leveringstider
delivery:
    uv run bilka_cli.py delivery

# Vis hvad en bestilling ville koste (sender ikke ordre)
checkout-dry:
    uv run bilka_cli.py checkout

# Log ind og gem session
login:
    uv run bilka_cli.py login

# Log ud
logout:
    uv run bilka_cli.py logout

# Start MCP-serveren
serve:
    uv run --extra mcp server.py
