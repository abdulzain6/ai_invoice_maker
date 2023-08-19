import random
import langchain
import pandas as pd
from langchain.chat_models import ChatOpenAI
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from langchain.chains import create_extraction_chain_pydantic
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from fuzzywuzzy import process
import pdfkit





class Order(BaseModel):
    customer_detail: str = Field(description="Details about the customer")
    payment_amount: str = Field(description="The amount of payment")
    bank_name: Optional[str] = Field(description="The name of the bank")
    payment_name_or_number: Optional[str] = Field(
        description="The name or number of the payment"
    )
    product_names: Optional[List[str]] = Field(description="Names of the products", default=[])
    company_name: str = Field(description="Name of the company")

class OrderExtractor:
    def __init__(self, openai_api_key: str) -> None:
        self.openai_api_key = openai_api_key
        self.llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0, verbose=True, openai_api_key=self.openai_api_key)

    def extract_order(self, prompt: str) -> Order:
        chain = create_extraction_chain_pydantic(pydantic_schema=Order, llm=self.llm)
        return chain.run(prompt)
    
class InvoiceGenerator:
    def __init__(self, html_template_path: str, product_file_path: str, html_dir: str = "html") -> None:
        self.html_path = html_template_path
        self.env = Environment(loader=FileSystemLoader(html_dir))
        self.template = self.env.get_template(self.html_path)
        
        self.load_product_file(product_file_path)
        self.context = {} 

    def load_product_file(self, file_path: str) -> 'InvoiceGenerator':
        file_extension = file_path.split('.')[-1]
        if file_extension == 'csv':
            self.products_df = pd.read_csv(file_path)
        elif file_extension == 'xlsx':
            self.products_df = pd.read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_extension}")
        return self

    def load_template(self) -> 'InvoiceGenerator':
        self.template = self.env.get_template(self.html_path)
        return self

    def render_customer_details(self, customer_details: List[str]) -> 'InvoiceGenerator':    
        customer_details_html = "".join(
            '<tr>\n<td style="font-size: 14px;color: #000;font-family: arial;text-align: left;line-height: 20px;">\n'
            + detail
            + '\n</td>\n</tr>\n'
            for detail in customer_details
        )
        self.context['customer_details'] = customer_details_html
        return self

    def render_payment_details(self, account_holder: str, bank_name: str, sort_code: str, account_number: str, bank_address: str) -> 'InvoiceGenerator':
        payment_details_html = (
            '<p style="font-size: 13px;color: #000;font-family: arial;text-align: left;line-height: 20px;">Account'
            f'holder: <strong>{account_holder}</strong> &nbsp; Bank: <strong>{bank_name}</strong> &nbsp; Sort code:'
            f'<strong>{sort_code}</strong> &nbsp; Account No: <strong>{account_number}</strong> &nbsp; Bank address: <strong>{bank_address}'
            '</strong></p>'
        )
        self.context['payment_details'] = payment_details_html
        return self

    def render_invoice_table(self, product_names: Optional[List[str]], total_amount: float, quantity: int = 10) -> 'InvoiceGenerator':
        product_total = total_amount / 1.2
        vat = total_amount / 6
        invoice_df = self.generate_invoice_products(product_names, product_total)
        data_rows = []
        for _, row in invoice_df.iterrows():
            if row['DESCRIPTION'] == 'Delivery':
                # Special formatting for delivery charges
                data_rows.append(f"""
                <tr>
                    <td style="font-size: 14px;color: #000;font-family: arial;text-align: left;line-height: 20px; padding: 10px 15px; border-top: 2px solid #797778;">
                        <strong>{row['DESCRIPTION']}</strong>
                    </td>
                    <td style="font-size: 14px;color: #000;font-family: arial;text-align: right;line-height: 20px; padding: 10px 15px; border-top: 2px solid #797778;">
                        <strong>{row['QUANTITY']}</strong>
                    </td>
                    <td style="font-size: 14px;color: #000;font-family: arial;text-align: right;line-height: 20px; padding: 10px 15px; border-top: 2px solid #797778;">
                        <strong>{row['UNIT PRICE (£)']}</strong>
                    </td>
                    <td style="font-size: 14px;color: #000;font-family: arial;text-align: right;line-height: 20px; padding: 10px 15px; border-top: 2px solid #797778;">
                        <strong>{row['AMOUNT (£)']}</strong>
                    </td>
                </tr>
                """)
            else:
                data_rows.append(f"""
                <tr>
                    <td style="font-size: 14px;color: #000;font-family: arial;text-align: left;line-height: 20px; padding: 10px 15px;">
                        {row['DESCRIPTION']}
                    </td>
                    <td style="font-size: 14px;color: #000;font-family: arial;text-align: right;line-height: 20px; padding: 10px 15px;">
                        {row['QUANTITY']}
                    </td>
                    <td style="font-size: 14px;color: #000;font-family: arial;text-align: right;line-height: 20px; padding: 10px 15px;">
                        {row['UNIT PRICE (£)']}
                    </td>
                    <td style="font-size: 14px;color: #000;font-family: arial;text-align: right;line-height: 20px; padding: 10px 15px;">
                        {row['AMOUNT (£)']}
                    </td>
                </tr>
                """)

        self.context['invoice_table'] = "\n".join(data_rows)
        self.context['vat'] = round(vat, 1)
        self.context['total'] = round(product_total, 1)
        self.context["full_amt"] = total_amount
        return self

    def render_invoice_details(self, invoice_number: str) -> 'InvoiceGenerator':
        self.context['invoice_number'] = invoice_number
        self.context['date'] = datetime.now().strftime("%d/%m/%Y")
        return self
    
    def render_company_info(self, company_info: Dict[str, str]) -> 'InvoiceGenerator':
        self.context.update(company_info)
        return self
    
    def render_company_logo(self, logo_path: str, width: str = None, height: str = None) -> 'InvoiceGenerator':
        logo_html = f'<img src="{logo_path}"'
        if width is not None:
            logo_html += f' width="{width}"'
        if height is not None:
            logo_html += f' height="{height}"'
        logo_html += '>'
        self.context['company_logo'] = logo_html
        return self
        

    def generate_invoice_products(self, product_names: Optional[List[str]], total_amount: float) -> pd.DataFrame:
        # If no product names are provided, select from all products
        if not product_names:
            available_products_df = self.products_df
        else:
            # Use fuzzy matching to find the best matches for each product name in the product_names list
            matched_product_names = [process.extractOne(product_name, self.products_df['Product'].unique())[0] for product_name in product_names]
            # Filter products_df to only include rows where the product name is in matched_product_names
            available_products_df = self.products_df[self.products_df['Product'].isin(matched_product_names)]
        
        # Initialize an empty DataFrame to store the selected products
        selected_products_df = pd.DataFrame(columns=['DESCRIPTION', 'QUANTITY', 'UNIT PRICE (£)', 'AMOUNT (£)'])
        
        # Initialize a variable to keep track of the total cost of the selected products
        total_cost = 0.0

        # Start a loop to select 7 to 20 products and add them to the invoice
        num_products = random.randint(7, 20)
        for _ in range(num_products):
            if len(available_products_df) > 0:
                # Randomly select a product
                selected_product = available_products_df.sample().reset_index(drop=True)
                max_available_quantity = max(int(qty) for qty in map(str, selected_product.columns) if qty.isdigit())
                product_price = selected_product.loc[0, str(max_available_quantity)] if str(max_available_quantity) in selected_product.columns else selected_product.loc[0, 'Price']
                product_cost = 10 * product_price  # We consider each pack as a unit of 10
                
                # Add this product to the invoice and update the total cost if it doesn't exceed the total amount
                if total_cost + product_cost <= total_amount:
                    selected_product_df = pd.DataFrame(
                    [{
                        'DESCRIPTION': f"{selected_product.loc[0, 'Product']} - {selected_product.loc[0, 'Flavour']}",
                        'QUANTITY': 10,  # We consider each pack as a unit of 10
                        'UNIT PRICE (£)': round(product_price, 2),
                        'AMOUNT (£)': round(product_cost, 2),
                    }]
                    )
                    selected_products_df = pd.concat([selected_products_df, selected_product_df], ignore_index=True)
                    total_cost += product_cost

                    # Remove the selected product from the available products
                    available_products_df = available_products_df[available_products_df.index != selected_product.index[0]]

        # If the total cost is still less than the total amount after selecting the products, try to increase the quantities of the already selected products
        while total_cost + 30 < total_amount and len(selected_products_df) > 0:  # Add a condition to ensure the delivery charge doesn't exceed 30
            # Flag to check if any product's quantity was increased
            increased = False
            
            for i, row in selected_products_df.iterrows():
                if row['QUANTITY'] >= 30:  # We limit the total quantity of each product to 30 packs (300 units)
                    continue
                    
                product_name, product_flavour = row['DESCRIPTION'].split(' - ')
                product_df = self.products_df[(self.products_df['Product'] == product_name) & (self.products_df['Flavour'] == product_flavour)]
                quantity = (row['QUANTITY'] + 10) * 10  # We consider each pack as a unit of 10
                
                # Get the price for the quantity from the product dataframe
                if str(quantity) in product_df.columns:
                    product_price = product_df.loc[product_df.index[0], str(quantity)]
                else:
                    # If the exact quantity is not present, use the price for the highest quantity less than the current quantity
                    available_quantities = [int(qty) for qty in map(str, product_df.columns) if qty.isdigit() and int(qty) < quantity]
                    highest_available_quantity = max(available_quantities) if available_quantities else 'Price'
                    product_price = product_df.loc[product_df.index[0], str(highest_available_quantity)]
                
                product_cost = quantity * product_price
                
                # Check if increasing the quantity of this product will cause the total cost to exceed the total amount
                if total_cost - row['AMOUNT (£)'] + product_cost > total_amount - 30:  # Add a condition to ensure the delivery charge doesn't exceed 30
                    # If it will, skip this product and try the next one
                    continue
                
                # If it won't, increase the quantity of this product and update the total cost
                selected_products_df.loc[i, 'QUANTITY'] += 10  # We consider each pack as a unit of 10
                selected_products_df.loc[i, 'UNIT PRICE (£)'] = round(product_price, 2)
                selected_products_df.loc[i, 'AMOUNT (£)'] = round(product_cost, 2)
                total_cost = total_cost - row['AMOUNT (£)'] + product_cost
                
                # Set the flag to True as the quantity of a product was increased
                increased = True
                break  # Break the loop as soon as a product's quantity is increased
            
            # If no product's quantity was increased, break the loop
            if not increased:
                break

        # Calculate the delivery charge as the difference between the target amount and the total cost of the products
        delivery_charges = round(max(0, total_amount - total_cost), 2)
        # Ensure the delivery charge doesn't exceed 30
        delivery_charges = min(30, delivery_charges)
        
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
    
    
    def get_rendered_html(self) -> str:
        return self.template.render(self.context)
    
    
    def html_to_pdf(self, output_file_path: str) -> 'InvoiceGenerator':
        pdfkit.from_string(self.get_rendered_html(), output_file_path, options={"enable-local-file-access": True})
        return self


        
    
if __name__ == "__main__":
    company_info = {
        "company_name": "XYZ Ltd",
        "address": "123 Road",
        "city": "London",
        "postcode": "HU12 8DN",
        "country": "United Kingdom",
        "company_reg_no": "7173728",
        "vat_reg": "VAT Reg.",
        "vat_no": "GB9282822",
        "email": "info@xyz.com"
    }
    generator = (InvoiceGenerator('invoice.html', "products.xlsx")
                .load_template()
                .render_customer_details(["Google Ltd", "123 Road", "London", "L28 je83"])
                .render_payment_details("Xyz Ltd", "Tide", "23-89-62", "73738282", "123 Road, London, JY71 1KL")
                .render_invoice_details("ABC123")
                .render_company_logo("file:///home/zain/ai_invoice_maker/logos/google.png", 200, 160)
                .render_invoice_table(None, 200)
                .render_company_info(company_info)
                .html_to_pdf("generated.pdf")
                )
    
    exit()
