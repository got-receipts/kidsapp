from urllib.parse import quote_plus

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


PHOTOS = {
    "building": "https://images.unsplash.com/photo-1587654780291-39c9404d746b?auto=format&fit=crop&w=720&q=75",
    "stem": "https://images.unsplash.com/photo-1581092921461-eab62e97a780?auto=format&fit=crop&w=720&q=75",
    "creative": "https://images.unsplash.com/photo-1513364776144-60967b0f800f?auto=format&fit=crop&w=720&q=75",
    "games": "https://images.unsplash.com/photo-1605901309584-818e25960a8f?auto=format&fit=crop&w=720&q=75",
    "outdoor": "https://images.unsplash.com/photo-1546519638-68e109498ffc?auto=format&fit=crop&w=720&q=75",
    "electronics": "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=720&q=75",
    "pretend": "https://images.unsplash.com/photo-1596461404969-9ae70f2830c1?auto=format&fit=crop&w=720&q=75",
}


STARTER_PRODUCTS = [
    ("LEGO Classic Medium Creative Brick Box", "Colorful open-ended building set.", 3499, "building", 4, True),
    ("LEGO City Police Car", "Buildable police car play set.", 999, "building", 5, False),
    ("LEGO Creator 3-in-1 Mighty Dinosaurs", "Build three dinosaur models.", 1499, "building", 7, True),
    ("LEGO Friends Mobile Bakery Food Cart", "Build-and-play bakery cart.", 999, "building", 6, False),
    ("LEGO Technic Monster Jam Dragon", "Pull-back monster truck building set.", 1999, "building", 7, False),
    ("LEGO Minecraft The Fox Lodge", "Minecraft-inspired building adventure.", 1999, "building", 8, False),
    ("MAGNA-TILES Classic 32-Piece Set", "Magnetic building shapes.", 4999, "building", 3, True),
    ("Mega Bloks Big Building Bag", "Large toddler-friendly building blocks.", 1699, "building", 1, False),
    ("National Geographic Crystal Growing Kit", "Grow and display crystals.", 1999, "stem", 8, True),
    ("Snap Circuits Jr. SC-100", "Snap-together electronics experiments.", 3499, "stem", 8, True),
    ("KiwiCo Science of Cooking Kit", "Hands-on food science activities.", 2995, "stem", 5, False),
    ("Thames & Kosmos Robotics Smart Machines", "Build programmable robots.", 6995, "stem", 8, True),
    ("GeoSafari Jr. Talking Microscope", "Kid-friendly viewing and learning.", 2499, "stem", 3, False),
    ("Osmo Genius Starter Kit", "Interactive learning play system.", 9999, "stem", 6, False),
    ("4M Solar Rover Kit", "Build a solar-powered vehicle.", 1999, "stem", 8, False),
    ("Learning Resources Coding Critters", "Screen-free coding play.", 4499, "stem", 4, False),
    ("Crayola Inspiration Art Case", "Portable coloring and drawing collection.", 2499, "creative", 5, True),
    ("Play-Doh Kitchen Creations Set", "Shape pretend food and treats.", 1999, "creative", 3, False),
    ("Melissa & Doug Deluxe Standing Easel", "Double-sided creative art station.", 7999, "creative", 3, True),
    ("Rainbow Loom Combo Set", "Create wearable bracelet designs.", 1999, "creative", 7, False),
    ("Klutz Make Your Own Soap Craft Kit", "Make colorful shaped soaps.", 2199, "creative", 8, False),
    ("Spirograph Deluxe Design Set", "Create geometric drawing patterns.", 2999, "creative", 8, False),
    ("Lite-Brite Ultimate Classic", "Build glowing picture art.", 1499, "creative", 4, False),
    ("Nintendo Switch Sports", "Active sports video game.", 4999, "games", 7, True),
    ("Mario Kart 8 Deluxe", "Family racing video game.", 5999, "games", 7, True),
    ("Minecraft for Nintendo Switch", "Creative building video game.", 2999, "games", 7, False),
    ("UNO Card Game", "Classic fast family card game.", 699, "games", 7, False),
    ("Connect 4 Game", "Four-in-a-row strategy game.", 999, "games", 6, False),
    ("Guess Who? Game", "Mystery character guessing game.", 1299, "games", 6, False),
    ("Ticket to Ride First Journey", "Introductory family board game.", 3499, "games", 6, False),
    ("Razor A Kick Scooter", "Foldable outdoor kick scooter.", 3999, "outdoor", 5, True),
    ("Nerf Elite Junior Blaster", "Easy-play foam dart blaster.", 1999, "outdoor", 6, False),
    ("Little Tikes T-Ball Set", "Starter baseball play set.", 1999, "outdoor", 2, False),
    ("Franklin Kids Soccer Goal Set", "Backyard soccer practice set.", 2999, "outdoor", 4, False),
    ("Melissa & Doug Sunny Patch Sprinkler", "Outdoor water-play sprinkler.", 2499, "outdoor", 3, False),
    ("Flybar My First Foam Pogo Jumper", "Beginner bounce jumper.", 1699, "outdoor", 3, False),
    ("Schwinn Koen 16-Inch Kids Bike", "Beginner bicycle with training wheels.", 17999, "outdoor", 4, True),
    ("Amazon Fire HD 10 Kids Tablet", "Kids tablet with protective case.", 18999, "electronics", 3, True),
    ("Toniebox Audio Player Starter Set", "Screen-free story audio player.", 9999, "electronics", 3, True),
    ("VTech KidiZoom Creator Cam", "Kid-friendly video creator camera.", 6999, "electronics", 5, False),
    ("JBL Jr 310BT Kids Headphones", "Wireless volume-limited headphones.", 4995, "electronics", 3, False),
    ("Nintendo Switch Lite", "Handheld gaming console.", 19999, "electronics", 7, True),
    ("Fitbit Ace 3 Activity Tracker", "Kids movement and activity tracker.", 7995, "electronics", 6, False),
    ("Kindle Kids E-Reader", "Reading device with kid-friendly case.", 12999, "electronics", 6, False),
    ("Barbie Dreamhouse Playset", "Large doll house play environment.", 17999, "pretend", 3, True),
    ("Hot Wheels City Ultimate Garage", "Multi-level vehicle play garage.", 9999, "pretend", 4, True),
    ("Bluey Family Home Playset", "Pretend family home play set.", 3999, "pretend", 3, False),
    ("Disney Princess Dress Up Trunk", "Costume dress-up collection.", 3999, "pretend", 3, False),
    ("Melissa & Doug Wooden Play Kitchen", "Wooden pretend kitchen center.", 19999, "pretend", 3, True),
    ("Fisher-Price Little People Farm", "Toddler farm pretend-play set.", 4499, "pretend", 1, False),
]


def seed_starter_products(apps, schema_editor):
    Product = apps.get_model("rewards", "ShoppingProduct")
    products = []
    for name, description, cents, category, suggested_age, featured in STARTER_PRODUCTS:
        products.append(
            Product(
                name=name,
                description=f"{description} Suggested age {suggested_age}+.",
                retailer="Google Shopping search",
                retailer_url=f"https://www.google.com/search?tbm=shop&q={quote_plus(name)}",
                image_url=PHOTOS[category],
                retail_price_cents=cents,
                category=category,
                featured=featured,
            )
        )
    Product.objects.bulk_create(products)


def remove_starter_products(apps, schema_editor):
    Product = apps.get_model("rewards", "ShoppingProduct")
    Product.objects.filter(name__in=[product[0] for product in STARTER_PRODUCTS], added_by__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("rewards", "0020_punishment_reversals_and_call_allowance")]

    operations = [
        migrations.AlterField(
            model_name="ledgerrequest",
            name="kind",
            field=models.CharField(
                choices=[
                    ("chore", "Chore reward"),
                    ("goal", "Growth goal reward"),
                    ("store", "Store purchase"),
                    ("spend", "Spend money"),
                    ("convert", "Legacy conversion (disabled)"),
                    ("cash_out", "Cash out"),
                    ("award", "Guardian award"),
                    ("star", "Good behavior star"),
                    ("transfer", "Move to spending"),
                    ("balance", "Balance correction"),
                    ("penalty", "Quest not verified"),
                    ("behavior", "Behavior deduction"),
                    ("gift", "Family transfer"),
                    ("call", "Family call"),
                    ("reversal", "Punishment removed"),
                    ("shopping", "Shopping order"),
                ],
                max_length=12,
            ),
        ),
        migrations.AlterField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[
                    ("chore", "New chore"),
                    ("reward", "Token reward"),
                    ("rule", "Rule update"),
                    ("grounded", "Grounded mode"),
                    ("wallet", "Wallet update"),
                    ("store", "Store purchase"),
                    ("message", "Message"),
                    ("call", "Call"),
                    ("shopping", "Shopping order"),
                ],
                max_length=12,
            ),
        ),
        migrations.CreateModel(
            name="ShoppingProduct",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("description", models.CharField(blank=True, max_length=220)),
                ("retailer", models.CharField(default="Google Shopping", max_length=60)),
                ("retailer_url", models.URLField(max_length=500)),
                ("image_url", models.URLField(blank=True, max_length=500)),
                ("retail_price_cents", models.PositiveIntegerField()),
                ("category", models.CharField(choices=[("building", "Building sets"), ("stem", "STEM & learning"), ("creative", "Arts & crafts"), ("games", "Games & puzzles"), ("outdoor", "Outdoor play"), ("electronics", "Kids electronics"), ("pretend", "Pretend play")], max_length=14)),
                ("active", models.BooleanField(default=True)),
                ("in_stock", models.BooleanField(default=True)),
                ("featured", models.BooleanField(default=False)),
                ("minimum_age", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("added_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shopping_products_added", to="rewards.profile")),
            ],
            options={"ordering": ["category", "name"]},
        ),
        migrations.CreateModel(
            name="ShoppingCartItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("added_at", models.DateTimeField(auto_now_add=True)),
                ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_cart_items", to="rewards.profile")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cart_items", to="rewards.shoppingproduct")),
            ],
            options={"ordering": ["added_at"]},
        ),
        migrations.CreateModel(
            name="ShoppingOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("submitted", "Sent to parent"), ("claimed", "Being purchased"), ("purchased", "Purchased"), ("canceled", "Canceled"), ("delivered", "Delivered")], default="submitted", max_length=12)),
                ("quoted_total_cents", models.PositiveIntegerField()),
                ("held_cash_cents", models.PositiveIntegerField(default=0)),
                ("held_spending_cents", models.PositiveIntegerField(default=0)),
                ("final_total_cents", models.PositiveIntegerField(blank=True, null=True)),
                ("parent_note", models.CharField(blank=True, max_length=240)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("purchased_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("canceled_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shopping_orders_assigned", to="rewards.profile")),
                ("child", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_orders", to="rewards.profile")),
                ("reservation_ledger", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shopping_order", to="rewards.ledgerrequest")),
            ],
            options={"ordering": ["-submitted_at"]},
        ),
        migrations.CreateModel(
            name="ShoppingOrderItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product_name", models.CharField(max_length=120)),
                ("retailer", models.CharField(max_length=60)),
                ("retailer_url", models.URLField(max_length=500)),
                ("image_url", models.URLField(blank=True, max_length=500)),
                ("unit_price_cents", models.PositiveIntegerField()),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="rewards.shoppingorder")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="order_items", to="rewards.shoppingproduct")),
            ],
            options={"ordering": ["pk"]},
        ),
        migrations.AddConstraint(
            model_name="shoppingcartitem",
            constraint=models.UniqueConstraint(fields=("child", "product"), name="one_product_per_child_shopping_cart"),
        ),
        migrations.AddConstraint(
            model_name="shoppingcartitem",
            constraint=models.CheckConstraint(condition=Q(("quantity__gte", 1)), name="shopping_cart_quantity_at_least_one"),
        ),
        migrations.RunPython(seed_starter_products, remove_starter_products),
    ]
