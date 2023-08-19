import pandas as pd
import numpy as np
from typing import Optional, List
from fuzzywuzzy import process
import random
# Load the data
products_df = pd.read_excel("products.xlsx")

# Display the first few rows


def generate_invoice_products_v9(products_df: pd.DataFrame, product_names: Optional[List[str]], total_amount: float) -> pd.DataFrame:
    # If no product names are provided, select from all products
    if not product_names:
        available_products_df = products_df
    else:
        # Use fuzzy matching to find the best matches for each product name in the product_names list
        matched_product_names = [process.extractOne(product_name, products_df['Product'].unique())[0] for product_name in product_names]
        # Filter products_df to only include rows where the product name is in matched_product_names
        available_products_df = products_df[products_df['Product'].isin(matched_product_names)]
    
    # Randomly select 7 to 20 products
    num_products = random.randint(7, 20)
    selected_products = available_products_df.sample(n=num_products).reset_index(drop=True)
    
    # Initialize an empty DataFrame to store the selected products
    selected_products_df = pd.DataFrame(columns=['DESCRIPTION', 'QUANTITY', 'UNIT PRICE (£)', 'AMOUNT (£)'])
    
    # Initialize a list to store the quantity for each product
    quantities = [10] * num_products

    # Loop until the total cost is greater than or equal to the total amount or the maximum number of rounds has been reached
    max_rounds = 100
    for _ in range(max_rounds):
        # Initialize a variable to keep track of the total cost of the selected products
        total_cost = 0.0

        # Calculate the cost for the current quantities
        for i, product in selected_products.iterrows():
            quantity = quantities[i]
            product_price = product[str(quantity)] if str(quantity) in product else product['Price']
            product_cost = quantity * product_price
            total_cost += product_cost

        # If the total cost is greater than or equal to the total amount, break the loop
        if total_cost >= total_amount:
            break

        # Try to increase the quantity of each product in a round-robin manner
        for i, product in selected_products.iterrows():
            # Get the current quantity and price
            quantity = quantities[i]
            product_price = product[str(quantity)] if str(quantity) in product else product['Price']
            
            # Check if we can increase the quantity without exceeding the total amount
            next_quantity = quantity + 10
            next_price_col = str(next_quantity)
            
            if next_price_col in product:
                next_price = product[next_price_col]
                next_cost = next_quantity * next_price
                
                if total_cost - quantity * product_price + next_cost <= total_amount:
                    # If we can increase the quantity without exceeding the total amount, do so
                    quantities[i] = next_quantity
                    total_cost = total_cost - quantity * product_price + next_cost
                else:
                    # If we cannot increase the quantity without exceeding the total amount, move on to the next product
                    continue
    
    # After all products have been updated, add them to the invoice
    for i, product in selected_products.iterrows():
        quantity = quantities[i]
        product_price = product[str(quantity)] if str(quantity) in product else product['Price']
        product_cost = quantity * product_price
        
        selected_product_df = pd.DataFrame(
        [{
            'DESCRIPTION': f"{product['Product']} - {product['Flavour']} (Pack of {quantity})",
            'QUANTITY': quantity // 10,  # We consider each pack as a unit of 10
            'UNIT PRICE (£)': round(product_price, 1),
            'AMOUNT (£)': round(product_cost, 1),
        }]
        )
        selected_products_df = pd.concat([selected_products_df, selected_product_df], ignore_index=True)

    # Calculate the delivery charge as the difference between the target amount and the total cost of the products
    delivery_charges = round(max(0, total_amount - total_cost), 1)
    
    # Add delivery charges as a separate row in the DataFrame
    delivery_charge_df = pd.DataFrame(
            [{
                'DESCRIPTION': 'Delivery',
                'QUANTITY': 1,
                'UNIT PRICE (£)': delivery_charges,
                'AMOUNT (£)': delivery_charges,
            }]
        )
    selected_products_df = pd.concat([selected_products_df, delivery_charge_df], ignore_index=True)
    
    return selected_products_df

# Test the function with a product name
invoice_df_with_product_name = generate_invoice_products_v9(products_df, ['Elf Bar 600'], 5000)
total_cost_with_product_name = invoice_df_with_product_name['AMOUNT (£)'].sum()
print(f"Total cost with product name: £{total_cost_with_product_name}")

# Test the function with None as the product name
invoice_df_with_None = generate_invoice_products_v9(products_df, None, 5000)
total_cost_with_None = invoice_df_with_None['AMOUNT (£)'].sum()
print(f"Total cost with None: £{total_cost_with_None}")
