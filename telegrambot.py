import json
import logging, uuid
import traceback
import os
import re


from aiogram.types.input_file import InputFile
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ContentType
from utils import read_password_from_json, extract_number_and_convert_to_float
from database import CompanyDBManager, SqliteDatabase
from ai import InvoiceGenerator, OrderExtractor

logging.basicConfig(level=logging.INFO)


class Form(StatesGroup):
    password = State()
    name = State()
    address1 = State()
    address2 = State()
    city = State()
    postcode = State()
    country = State()
    email = State()
    company_number = State()
    vat_reg = State()
    vat_number = State()
    logo = State()
    invoice_number = State()


class PaymentForm(StatesGroup):
    password = State()  # State for the password
    company_name = State()  # State for the company name
    payment_name = State()  # State for the payment name
    bank_name = State()  # State for the bank name
    account_number = State()  # State for the account number
    sort_code = State()  # State for the sort code
    bank_address = State()  # State for the bank address


class OrderForm(StatesGroup):
    customer_detail = State()
    payment_amount = State()
    bank_name = State()
    payment_name_or_number = State()
    product_names = State()
    company_name = State()


class OrderForm(StatesGroup):
    customer_detail = State()
    payment_amount = State()
    bank_name = State()
    payment_name_or_number = State()
    product_names = State()
    company_name = State()


class Conversation:
    def __init__(self, bot):
        self.bot = bot
        self.dp = bot.dp

    async def start(self, message: types.Message):
        raise NotImplementedError

    async def cancel_handler(self, message: types.Message, state: FSMContext):
        await message.answer(
            "Operation cancelled.", reply_markup=types.ReplyKeyboardRemove()
        )
        await state.finish()


class MyBot:
    def __init__(self, token: str, db: CompanyDBManager):
        self.bot = Bot(token=token)
        self.dp = Dispatcher(self.bot, storage=MemoryStorage())
        self.db = db
        self.add_company = AddCompanyConversation(self)
        self.add_payment = PaymentConversation(self)
        self.add_order = OrderConversation(self)

        self.dp.register_message_handler(
            self.change_password, Command("change_password")
        )
        self.dp.register_message_handler(self.list_invoices, Command("list_invoices"))
        self.dp.register_message_handler(self.get_invoice, Command("get_invoice"))
        self.dp.register_message_handler(self.get_companies, Command("get_companies"))
        self.dp.register_message_handler(self.delete_company, Command("delete_company"))
        self.dp.register_message_handler(self.list_payments, commands="list_payments")
        self.dp.register_message_handler(self.delete_payment, commands="delete_payment")
        self.dp.register_message_handler(
            self.add_order_from_string, Command("add_order_from_string")
        )
        self.dp.register_message_handler(self.unknown_message)

    async def add_order_from_string(self, message: types.Message):
        try:
        # Get the order string from the message
            order_string = message.get_args()
            
            if not order_string:
                await message.answer("Please provide the order details in the following format: \n"
                                    "Customer detail\n"
                                    "Payment amount\n"
                                    "Bank name (optional)\n"
                                    "Payment name or number (optional)\n"
                                    "Product names (separated by commas)\n"
                                    "Company name\n"
                                    "For example: /add_order_from_string \"John Doe, 123 Main St, City, Country\\n$1000\\nBank of America\\nPayment 123\\nProduct1, Product2, Product3\\nMy Company\"")
                return

            
            # Extract the fields from the order string
            order_extractor = OrderExtractor(openai_api_key="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")
            order = order_extractor.extract_order(order_string)[0]
            print(order)
            # Get the company from the database
            company = self.db.get_company_by_name(order.company_name)
            if not company:
                await message.answer(f"No company found with the name '{order.company_name}'.")
                return
            
            choice =  order.payment_name_or_number or order.bank_name
            # Get the payment from the database
            payment = self.db.get_payment_by_name_or_bank(order.company_name, choice)
            if not payment:
                await message.answer(f"No payment found with the name '{order.payment_name_or_number}' or '{order.bank_name}'.")
                return
            
            # Generate the PDF invoice
            invoice_generator = InvoiceGenerator("invoice.html", "products.xlsx")
            invoice_path = os.path.join(
                "invoices", f"{order.company_name}_{company.invoice_number}.pdf"
            )
            invoice_generator.load_template() \
                .render_customer_details(order.customer_detail.split("\n")) \
                .render_payment_details(**payment.to_dict()) \
                .render_invoice_details(company.invoice_number) \
                .render_company_logo(f"file://{os.path.abspath(company.logo)}", 200, 160) \
                .render_invoice_table(
                    product_names=order.product_names,
                    total_amount=extract_number_and_convert_to_float(order.payment_amount),
                ) \
                .render_company_info(company.to_dict()) \
                .html_to_pdf(invoice_path)
                
            self.db.update_company(
                order.company_name,
                **{
                    "invoice_number": self.db.increment_invoice_number(
                        company.invoice_number
                    )
                },
            )
            # Send the invoice
            with open(invoice_path, "rb") as file:
                await self.bot.send_document(message.from_user.id, InputFile(file, filename=f"{company.invoice_number}.pdf"))
        except Exception as e:
            await message.answer(f"An error occurred: {e}")
            raise e


    async def get_companies(self, message: types.Message):
        companies = self.db.get_all_company_names()
        companies_str = "\n".join([company.name for company in companies])
        await message.answer(f"Here are all the companies:\n\n{companies_str}")

    async def delete_company(self, message: types.Message):
        args = message.get_args()  # Get the command arguments
        if not args:
            await message.answer(
                'Please specify the company name. Example: /delete_company  "CompanyName" password'
            )
            return
        try:
            if match := re.match(r'"(.*?)"\s+(.+)', args):
                company_name = match[1]
                password = match[2]
            else:
                await message.answer(
                    'Invalid command format. Please use: /delete_company "CompanyName" password'
                )
                return
        except Exception:
            await message.answer(
                'Invalid command format. Please use: /delete_company "CompanyName" password'
            )
            return

        if password != read_password_from_json("creds.json"):
            await message.answer("Incorrect password. Please try again.")
            return

        if not self.db.company_exists(company_name):
            await message.answer("Company does not exist. Please try again.")
            return

        os.remove(self.db.get_company_by_name(company_name).logo)
        self.db.delete_company(company_name)

        await message.answer(f"Company '{company_name}' deleted successfully.")

    async def change_password(self, message: types.Message):
        args = message.get_args()  # Get the command arguments
        if not args:
            await message.answer(
                "Please specify the current password and the new password. Example: /change_password current_password new_password"
            )
            return

        try:
            if match := re.match(r"(\S+)\s+(\S+)", args):
                current_password = match[1]
                new_password = match[2]
            else:
                await message.answer(
                    "Invalid command format. Please use: /change_password current_password new_password"
                )
                return
        except Exception:
            await message.answer(
                "Invalid command format. Please use: /change_password current_password new_password"
            )
            return

        if current_password != read_password_from_json("creds.json"):
            await message.answer("Incorrect current password. Please try again.")
            return

        # Update the password in the JSON file
        with open("creds.json", "w") as f:
            json.dump({"password": new_password}, f)

        await message.answer("Password changed successfully.")

    async def list_payments(self, message: types.Message):
        args = message.get_args()  # Get the command arguments
        if not args:
            await message.answer(
                'Please specify the company name. Example: /list_payments "CompanyName"'
            )
            return
        try:
            if match := re.match(r'"(.*?)"', args):
                company_name = match[1]
            else:
                await message.answer(
                    'Invalid command format. Please use: /list_payments "CompanyName"'
                )
                return
        except Exception:
            await message.answer(
                'Invalid command format. Please use: /list_payments "CompanyName"'
            )
            return

        company_payments = self.db.get_payments_by_company_name(company_name)
        if company_payments is None:
            await message.answer(f"No company found with the name '{company_name}'.")
        elif not company_payments:
            await message.answer(f"No payments found for the company '{company_name}'.")
        else:
            payment_names = "\n".join(
                [payment.payment_name for payment in company_payments]
            )
            await message.answer(f"Payments for '{company_name}':\n{payment_names}")

    async def delete_payment(self, message: types.Message):
        args = message.get_args()  # Get the command arguments
        if not args:
            await message.answer(
                "Please specify the company name, payment name, and password. "
                'Example: /delete_payment "CompanyName" "PaymentName" password'
            )
            return
        try:
            if match := re.match(r'"(.*?)"\s+"(.*?)"\s+(.+)', args):
                company_name = match[1]
                payment_name = match[2]
                password = match[3]
            else:
                await message.answer(
                    "Invalid command format. Please use: "
                    '/delete_payment "CompanyName" "PaymentName" password'
                )
                return
        except Exception:
            await message.answer(
                "Invalid command format. Please use: "
                '/delete_payment "CompanyName" "PaymentName" password'
            )
            return

        correct_password = read_password_from_json("creds.json")
        if password != correct_password:
            await message.answer(
                "Incorrect password. You are not authorized to delete a payment."
            )
            return

        # Password is correct, proceed with deleting payment
        try:
            deleted_count = self.bot.db.delete_payment(company_name, payment_name)
            if deleted_count > 0:
                await message.answer(
                    f"Payment '{payment_name}' deleted successfully for company '{company_name}'."
                )
            else:
                await message.answer("No matching payment found. No payment deleted.")
        except Exception as e:
            await message.answer(f"Error deleting payment! Error: {e}")

    async def list_invoices(self, message: types.Message):
        if invoice_files := os.listdir("invoices"):
            invoice_names = [os.path.splitext(name)[0] for name in invoice_files]
            invoices = "\n".join(invoice_names)
            res = f"""Available invoices:\n{invoices}"""
            await message.answer(res)
        else:
            await message.answer("No invoices found.")

    async def get_invoice(self, message: types.Message):
        args = message.get_args()  # Get the command arguments
        if not args:
            await message.answer(
                'Please specify the invoice name (without the ".pdf" extension) and the password. '
                'Example: /get_invoice "InvoiceName" password'
            )
            return
        try:
            if match := re.match(r'"(.*?)"\s+(.+)', args):
                invoice_name = match[1]
                password = match[2]
            else:
                await message.answer(
                    'Invalid command format. Please use: /get_invoice "InvoiceName" password'
                )
                return
        except Exception:
            await message.answer(
                'Invalid command format. Please use: /get_invoice "InvoiceName" password'
            )
            return

        if password != read_password_from_json("creds.json"):
            await message.answer("Incorrect password. Please try again.")
            return

        invoice_path = os.path.join("invoices", f"{invoice_name}.pdf")
        if not os.path.exists(invoice_path):
            await message.answer(f"No invoice found with the name '{invoice_name}'.")
            return

        with open(invoice_path, "rb") as file:
            await self.bot.send_document(message.from_user.id, InputFile(file, filename=f"{invoice_name}.pdf"))

    def run(self):
        from aiogram import executor

        executor.start_polling(self.dp)

    async def unknown_message(self, message: types.Message):
        help_text = """
        Welcome to InvoiceBot! Here are some commands you can use:

        /add_order_from_string <order details>: Adds an order from a string. The order details should include the customer detail, payment amount, bank name (optional), payment name or number (optional), product names, and company name. Please ensure the information is correct.
        /new_company: Start a process to create a new company.
        /add_payment: Start a process to add a new payment method.
        /add_order: Start a process to add a new order.
        /change_password current_password new_password: Change the bot's password.
        /get_companies: Get a list of all companies.
        /delete_company "CompanyName" password: Remove a company.
        /list_payments "CompanyName": Get a list of all payments associated with a company.
        /delete_payment "CompanyName" "PaymentName" password: Remove a payment method associated with a specific company.
        /list_invoices: Get a list of all invoices.
        /get_invoice "InvoiceName" password: Get a specific invoice.

        Please replace placeholders like CompanyName, PaymentName, InvoiceName, current_password, new_password, and password with your actual values. Make sure to include quotes (") around names if they contain spaces.
        """
        await message.reply(help_text)



class AddCompanyConversation(Conversation):
    def __init__(self, bot: MyBot, command_name: str = "new_company"):
        super().__init__(bot)
        self.bot = bot
        self.dp.register_message_handler(self.start, Command(command_name), state="*")
        self.dp.register_message_handler(self.process_password, state=Form.password)
        self.dp.register_message_handler(self.process_name, state=Form.name)
        self.dp.register_message_handler(self.process_address1, state=Form.address1)
        self.dp.register_message_handler(self.process_address2, state=Form.address2)
        self.dp.register_message_handler(self.process_city, state=Form.city)
        self.dp.register_message_handler(self.process_postcode, state=Form.postcode)
        self.dp.register_message_handler(self.process_country, state=Form.country)
        self.dp.register_message_handler(self.process_email, state=Form.email)
        self.dp.register_message_handler(
            self.process_company_number, state=Form.company_number
        )
        self.dp.register_message_handler(self.process_vat_reg, state=Form.vat_reg)
        self.dp.register_message_handler(self.process_vat_number, state=Form.vat_number)
        self.dp.register_message_handler(
            self.process_logo, content_types=ContentType.PHOTO, state=Form.logo
        )
        self.dp.register_message_handler(
            self.process_invoice_number, state=Form.invoice_number
        )
        self.dp.register_message_handler(
            self.cancel_handler, Command("cancel"), state="*"
        )

    async def start(self, message: types.Message):
        await message.answer("Please enter the password:")
        await Form.password.set()

    async def process_password(self, message: types.Message, state: FSMContext):
        password = read_password_from_json("creds.json")
        if message.text != password:
            await message.answer("Incorrect password. Please try again:")
            return
        await message.answer("Password accepted. Please enter the company name:")
        await Form.next()

    async def process_name(self, message: types.Message, state: FSMContext):
        name = message.text.strip()
        if not name:
            await message.answer("Company name cannot be empty. Please try again:")
            return
        if self.bot.db.company_exists(name):
            await message.answer("Company name already exists. Please try again:")
            return
        await state.update_data(name=name)
        await message.answer("Please enter the first line of the company address:")
        await Form.next()

    async def process_address1(self, message: types.Message, state: FSMContext):
        await state.update_data(address1=message.text)
        await message.answer(
            "Please enter the second line of the company address (Enter . for none):"
        )
        await Form.next()

    async def process_address2(self, message: types.Message, state: FSMContext):
        address2 = message.text if message.text != "." else ""
        await state.update_data(address2=address2)
        await message.answer("Please enter the city of the company:")
        await Form.next()

    async def process_city(self, message: types.Message, state: FSMContext):
        await state.update_data(city=message.text)
        await message.answer("Please enter the postcode of the company:")
        await Form.next()

    async def process_postcode(self, message: types.Message, state: FSMContext):
        await state.update_data(postcode=message.text)
        await message.answer("Please enter the country of the company:")
        await Form.next()

    async def process_country(self, message: types.Message, state: FSMContext):
        await state.update_data(country=message.text)
        await message.answer("Please enter the email of the company:")
        await Form.next()

    async def process_email(self, message: types.Message, state: FSMContext):
        email = message.text.strip()
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            await message.answer("Invalid email address. Please try again:")
            return
        await state.update_data(email=email)
        await message.answer("Please enter the company number:")
        await Form.next()

    async def process_company_number(self, message: types.Message, state: FSMContext):
        try:
            company_number = int(message.text.strip())
        except ValueError:
            await message.answer("Company number must be an integer. Please try again:")
            return
        await state.update_data(company_number=company_number)
        await message.answer(
            "Please enter the VAT registration descriptor (Enter . for default : VAT Reg.):"
        )
        await Form.next()

    async def process_vat_reg(self, message: types.Message, state: FSMContext):
        desc = message.text if message.text != "." else "VAT Reg."
        await state.update_data(vat_reg=desc)
        await message.answer("Please enter the VAT number:")
        await Form.next()

    async def process_vat_number(self, message: types.Message, state: FSMContext):
        await state.update_data(vat_number=message.text)
        await message.answer("Please upload the company's logo:")
        await Form.next()

    async def process_logo(self, message: types.Message, state: FSMContext):
        if not message.photo:
            await message.answer("No image provided. Please upload the company's logo.")
            return

        photo_id = message.photo[-1].file_id
        file_info = await self.bot.bot.get_file(photo_id)
        file_path = file_info.file_path

        os.makedirs("logos", exist_ok=True)
        destination = os.path.join("logos", f'{file_path.split("/")[-1]}')

        while os.path.exists(destination):
            destination = os.path.join("logos", f"{uuid.uuid4()}.jpg")

        await self.bot.bot.download_file(file_path, destination=destination)

        if os.path.exists(destination):
            await state.update_data(logo=destination)
            await message.answer(
                "Logo updated successfully. Please enter the company's invoice number:"
            )
            await Form.next()
        else:
            await message.answer(
                "There was an error updating the logo. Please try again."
            )
            await Form.logo.set()

    async def process_invoice_number(self, message: types.Message, state: FSMContext):
        invoice_number = message.text.strip()
        if not re.search(
            r"\d", invoice_number
        ):  # Check if there's at least one digit in the invoice_number
            await message.answer(
                "Invoice number must contain at least one number. Please try again:"
            )
            return
        await state.update_data(invoice_number=invoice_number)
        data = await state.get_data()
        # you can now process the data
        try:
            self.bot.db.add_company(**data)
            await message.answer("Successfully added company!")
        except Exception as e:
            await message.answer(f"Error adding company! Error: {e}")
        await state.finish()

    async def cancel_handler(self, message: types.Message, state: FSMContext):
        await message.answer(
            "Operation cancelled.", reply_markup=types.ReplyKeyboardRemove()
        )
        await state.finish()


class PaymentConversation(Conversation):
    def __init__(self, bot: MyBot):
        super().__init__(bot)
        self.bot = bot
        self.dp = self.bot.dp
        self.dp.register_message_handler(
            self.process_add_payment, Command("add_payment"), state="*"
        )
        self.dp.register_message_handler(
            self.process_password, state=PaymentForm.password
        )
        self.dp.register_message_handler(
            self.process_company_name, state=PaymentForm.company_name
        )
        self.dp.register_message_handler(
            self.process_payment_name, state=PaymentForm.payment_name
        )
        self.dp.register_message_handler(
            self.process_bank_name, state=PaymentForm.bank_name
        )
        self.dp.register_message_handler(
            self.process_account_number, state=PaymentForm.account_number
        )
        self.dp.register_message_handler(
            self.process_sort_code, state=PaymentForm.sort_code
        )
        self.dp.register_message_handler(
            self.process_bank_address, state=PaymentForm.bank_address
        )

    async def process_add_payment(self, message: types.Message):
        # Ask for the password first
        await message.answer("Please enter the password to add a payment:")
        await PaymentForm.password.set()

    async def process_password(self, message: types.Message, state: FSMContext):
        password = read_password_from_json("creds.json")
        if message.text != password:
            await message.answer(
                "Incorrect password. You are not authorized to add a payment."
            )
            await state.finish()
            return

        # Password is correct, proceed with adding payment
        await message.answer(
            "Password accepted. Please enter the company name for the payment:"
        )
        await PaymentForm.company_name.set()

    async def process_company_name(self, message: types.Message, state: FSMContext):
        await state.update_data(company_name=message.text)
        await message.answer("Please enter the payment name:")
        await PaymentForm.payment_name.set()

    async def process_payment_name(self, message: types.Message, state: FSMContext):
        await state.update_data(payment_name=message.text)
        await message.answer("Please enter the bank name for the payment:")
        await PaymentForm.bank_name.set()

    async def process_bank_name(self, message: types.Message, state: FSMContext):
        await state.update_data(bank_name=message.text)
        await message.answer("Please enter the account number for the payment:")
        await PaymentForm.account_number.set()

    async def process_account_number(self, message: types.Message, state: FSMContext):
        try:
            account_number = int(message.text.strip())
        except ValueError:
            await message.answer("Account number must be an integer. Please try again:")
            return
        await state.update_data(account_number=account_number)
        await message.answer("Please enter the sort code for the payment:")
        await PaymentForm.sort_code.set()

    async def process_sort_code(self, message: types.Message, state: FSMContext):
        await state.update_data(sort_code=message.text)
        await message.answer("Please enter the bank address for the payment:")
        await PaymentForm.bank_address.set()

    async def process_bank_address(self, message: types.Message, state: FSMContext):
        await state.update_data(bank_address=message.text)
        data = await state.get_data()
        company_name = data.get("company_name")
        if not company_name:
            await message.answer("Company name not provided. Please try again.")
            return

        try:
            company = self.bot.db.get_company_by_name(company_name)
            if not company:
                await message.answer(
                    "Company not found. Please check the company name."
                )
                return

            payment_data = {
                "company": company,
                "payment_name": data["payment_name"],
                "bank_name": data["bank_name"],
                "account_number": data["account_number"],
                "sort_code": data["sort_code"],
                "bank_address": data["bank_address"],
            }

            # Add the payment to the database
            payment = self.bot.db.add_payment(**payment_data)

            await message.answer(
                f"Payment '{data['payment_name']}' added successfully for company '{company_name}'."
            )
        except Exception as e:
            await message.answer(f"Error adding payment! Error: {e}")

        await state.finish()


class OrderConversation(Conversation):
    def __init__(self, bot: MyBot):
        super().__init__(bot)
        self.bot = bot
        self.dp = self.bot.dp

        self.dp.register_message_handler(self.start, Command("add_order"), state="*")
        self.dp.register_message_handler(
            self.process_company_name, state=OrderForm.company_name
        )
        self.dp.register_message_handler(
            self.process_customer_detail, state=OrderForm.customer_detail
        )
        self.dp.register_message_handler(
            self.process_payment_amount, state=OrderForm.payment_amount
        )
        self.dp.register_message_handler(
            self.process_bank_name, state=OrderForm.bank_name
        )
        self.dp.register_message_handler(
            self.process_payment_name_or_number, state=OrderForm.payment_name_or_number
        )
        self.dp.register_message_handler(
            self.process_product_names, state=OrderForm.product_names
        )

    async def start(self, message: types.Message):
        await message.answer("Please enter the name of the company:")
        await OrderForm.company_name.set()

    async def process_company_name(self, message: types.Message, state: FSMContext):
        company_name = message.text.strip()
        if not company_name:
            await message.answer(
                "Company name cannot be empty. Please enter the name of the company:"
            )
            return
        company = self.bot.db.get_company_by_name(company_name)
        if company is None:
            await message.answer(
                "Company not found. Please check the company name and try again."
            )
            return
        await state.update_data(company_name=company_name)
        await message.answer("Please enter the customer details:")
        await OrderForm.customer_detail.set()

    async def process_customer_detail(self, message: types.Message, state: FSMContext):
        customer_detail = message.text.strip()
        if not customer_detail:
            await message.answer(
                "Customer details cannot be empty. Please enter the customer details:"
            )
            return
        await state.update_data(customer_detail=customer_detail)
        await message.answer("Please enter the payment amount:")
        await OrderForm.payment_amount.set()

    async def process_payment_amount(self, message: types.Message, state: FSMContext):
        payment_amount = message.text.strip()
        await state.update_data(payment_amount=payment_amount)
        await message.answer("Please enter the bank name (Enter . for none):")
        await OrderForm.bank_name.set()

    async def process_bank_name(self, message: types.Message, state: FSMContext):
        bank_name = message.text.strip() if message.text.strip() != "." else None
        await state.update_data(bank_name=bank_name)
        await message.answer(
            "Please enter the payment name or number (Enter . for none):"
        )
        await OrderForm.payment_name_or_number.set()

    async def process_payment_name_or_number(
        self, message: types.Message, state: FSMContext
    ):
        payment_name_or_number = (
            message.text.strip() if message.text.strip() != "." else None
        )
        if not payment_name_or_number and not data.get("bank_name", None):
            await message.answer(
                "Payment name or number cannot be empty. Please enter the payment name or number:"
            )
            return
        data = await state.get_data()
        company_name = data.get("company_name")

        # Validate payment name or bank name
        payment = self.bot.db.get_payment_by_name_or_bank(
            company_name, payment_name_or_number
        )
        if payment is None:
            # If the payment name or bank name is incorrect, show the user the available options
            all_payments = self.bot.db.get_all_payments()
            payment_options = "\n".join(
                [
                    f"Payment Name: {p.payment_name}, Bank Name: {p.bank_name}"
                    for p in all_payments
                ]
            )
            await message.answer(
                f"Payment name or bank name not found. Here are the available options:\n\n{payment_options}\n\nPlease enter a valid payment name or bank name:"
            )
            return

        await state.update_data(payment_name_or_number=payment_name_or_number)
        await message.answer("Please enter the product names, separated by commas Enter . for all random:")
        await OrderForm.product_names.set()

    async def process_product_names(self, message: types.Message, state: FSMContext):
        if message.text == ".":
            product_names = None
        else:
            product_names = [product.strip() for product in message.text.split(",")]

        await state.update_data(product_names=product_names)

        data = await state.get_data()
        company = self.bot.db.get_company_by_name(data.get("company_name"))
        payment = self.bot.db.get_payment_by_name_or_bank(
            data.get("company_name"),
            data.get("payment_name_or_number", data.get("bank_name")),
        )

        os.makedirs("invoices", exist_ok=True)
        invoice_path = os.path.join(
            "invoices", f"{data.get('company_name')}_{company.invoice_number}.pdf"
        )

        try:
            (
                InvoiceGenerator("invoice.html", "products.xlsx")
                .load_template()
                .render_customer_details(data.get("customer_detail", "").split("\n"))
                .render_payment_details(**payment.to_dict())
                .render_invoice_details(company.invoice_number)
                .render_company_logo(f"file://{os.path.abspath(company.logo)}", 200, 160)
                .render_invoice_table(
                    data.get("product_names", None),
                    extract_number_and_convert_to_float(data.get("payment_amount", 10)),
                )
                .render_company_info(company.to_dict())
                .html_to_pdf(invoice_path)
            )

            self.bot.db.update_company(
                data.get("company_name"),
                **{
                    "invoice_number": self.bot.db.increment_invoice_number(
                        company.invoice_number
                    )
                },
            )

            with open(invoice_path, "rb") as file:
                await self.bot.bot.send_document(
                    message.from_user.id, types.InputFile(file, filename=invoice_path)
                )

            await message.answer(f"Invoice saved to {invoice_path}")
            await state.finish()
        except Exception as e:
            e = traceback.format_exc()
            logging.error(f"An error occurred: {e}")
            await message.answer("An error occurred. Please try again.")
            await state.finish()

    async def cancel_handler(self, message: types.Message, state: FSMContext):
        await message.answer(
            "Operation cancelled.", reply_markup=types.ReplyKeyboardRemove()
        )
        await state.finish()


if __name__ == "__main__":
    database = CompanyDBManager(SqliteDatabase("database.db"))
    bot = MyBot("6341170255:AAEJ0Wx_HLrf80Z264ZprbMpke6OPSw32Us", database)
    bot.run()
