import json
import re
from typing import List, Optional
from peewee import *
from peewee import Model


class CompanyDBManager:
    def __init__(self, db: PostgresqlDatabase) -> None:

        class Company(Model):
            name = CharField(primary_key=True)
            address1 = CharField()
            address2 = CharField(null=True)
            city = CharField()
            postcode = CharField()
            country = CharField()  # new field for the company's country
            email = CharField()
            company_number = IntegerField()
            vat_reg = CharField()  # new field for the VAT registration descriptor
            vat_number = CharField()
            logo = CharField(null=True)  # new field for the company's logo
            invoice_number = CharField()

            class Meta:
                database = db

            def to_dict(self) -> dict:
                return {
                    'company_name': self.name,
                    'address': self.address1,
                    'city': self.city,
                    'postcode': self.postcode,
                    'country': self.country,
                    'company_reg_no': str(self.company_number),
                    'vat_reg': self.vat_reg,
                    'vat_no': self.vat_number,
                    'email': self.email
                }

            def to_json(self) -> str:
                return json.dumps(self.to_dict())




        class Payment(Model):
            company = ForeignKeyField(Company, backref='payments')
            payment_name = CharField()
            bank_name = CharField()
            account_number = IntegerField()
            sort_code = CharField()
            bank_address = CharField()

            class Meta:
                database = db
                constraints = [SQL('UNIQUE(company_id, payment_name, bank_name)')]


            def to_dict(self) -> dict:
                return {
                    'account_holder': self.company.name,
                    'bank_name': self.bank_name,
                    'sort_code': self.sort_code,
                    'account_number': str(self.account_number),
                    'bank_address': self.bank_address,
                }

            def to_json(self) -> str:
                return json.dumps(self.to_dict())


        self.company_model: 'Model' = Company
        self.payment_model: 'Model' = Payment
        self.db: PostgresqlDatabase = db
        db.connect(reuse_if_open=True)
        db.create_tables([self.company_model, self.payment_model], safe=True)


    def company_exists(self, company_name: str) -> bool:
        with self.db.connection_context():
            return bool(self.company_model.select().where(self.company_model.name == company_name).exists())

    def is_valid(self, invoice_number: str) -> bool:
        for char in invoice_number:
            if char.isdigit():
                return True
        return False


    def increment_invoice_number(self, invoice_number: str) -> str:
        parts = re.split('([0-9]+)', invoice_number)  # split the string into numeric and non-numeric parts
        incremented_parts = []
        for part in parts:
            incremented_part = str(int(part) + 1) if part.isdigit() else part
            incremented_parts.append(incremented_part)
        return ''.join(incremented_parts)  # reassemble the stringe incremented invoice number
    
    def add_company(self, name: str, address1: str, address2: str, city: str, postcode: str, country: str, email: str, company_number: int, vat_reg: str, vat_number: str, logo: str, invoice_number: str) -> 'Model':
        with self.db.connection_context():
            
            if not self.is_valid(invoice_number):
                raise ValueError("Invalid invoice number.")
            
            return self.company_model.create(
                name=name,
                address1=address1,
                address2=address2,
                city=city,
                postcode=postcode,
                country=country,  # new field for the company's country
                email=email,
                company_number=company_number,
                vat_reg=vat_reg,  # new field for the VAT registration descriptor
                vat_number=vat_number,
                logo=logo,
                invoice_number=invoice_number
            )

    def add_payment(self, company: 'Model', payment_name: str, bank_name: str, account_number: int, sort_code: str, bank_address: str) -> 'Model':
        with self.db.connection_context():
            return self.payment_model.create(
                company=company,
                payment_name=payment_name,  # new field for the payment's name
                bank_name=bank_name,
                account_number=account_number,
                sort_code=sort_code,
                bank_address=bank_address,
            )

    def get_company_by_name(self, name: str) -> Optional['Model']:
        with self.db.connection_context():
            try:
                return self.company_model.get(self.company_model.name == name)
            except DoesNotExist:
                return None

    def get_payments_by_company_name(self, company_name: str) -> Optional[List['Model']]:
        with self.db.connection_context():
            if company := self.get_company_by_name(company_name):
                return list(company.payments)
            else:
                return None

    def get_all_companies(self) -> List['Model']:
        with self.db.connection_context():
            return list(self.company_model.select())
        
    def get_all_company_names(self) -> List['Model']:
        with self.db.connection_context():
            return list(self.company_model.select(self.company_model.name))

    def get_all_payments(self) -> List['Model']:
        with self.db.connection_context():
            return list(self.payment_model.select())

    def update_company(self, company_name: str, **kwargs) -> Optional['Model']:
        with self.db.connection_context():
            try:
                query = self.company_model.update(kwargs).where(self.company_model.name == company_name)
                query.execute()
                return self.get_company_by_name(company_name)
            except DoesNotExist:
                return None

    def delete_company(self, company_name: str) -> int:
        with self.db.connection_context():
            return self.company_model.delete().where(self.company_model.name == company_name).execute()

    def update_payment(self, company_name: str, payment_name: str, **kwargs) -> Optional['Model']:
        with self.db.connection_context():
            try:
                company = self.get_company_by_name(company_name)
                query = self.payment_model.update(kwargs).where((self.payment_model.company == company) & (self.payment_model.payment_name == payment_name))
                query.execute()
                return self.get_payments_by_company_name(company_name)
            except DoesNotExist:
                return None

    def delete_payment(self, company_name: str, payment_name: str) -> int:
        with self.db.connection_context():
            company = self.get_company_by_name(company_name)
            return self.payment_model.delete().where((self.payment_model.company == company) & (self.payment_model.payment_name == payment_name)).execute()

    def get_payment_by_name_or_bank(self, company_name: str, payment_name_or_bank: str) -> Optional['Model']:
        with self.db.connection_context():
            company = self.get_company_by_name(company_name)
            try:
                return self.payment_model.get((self.payment_model.company == company) & ((self.payment_model.payment_name == payment_name_or_bank) | (self.payment_model.bank_name == payment_name_or_bank)))
            except DoesNotExist:
                return None
            
            
if __name__ == "__main__":
    db = SqliteDatabase("database.db")
    db_manager = CompanyDBManager(db)
    
    print(db_manager.get_payment_by_name_or_bank("XYZ Ltd", "Tide"))
    exit()
    # Add a company
    company = db_manager.add_company(
        name='XYZ Ltd', 
        address1='123 Road', 
        address2='', 
        city='London', 
        postcode='SH12 8SK', 
        email='xyz@gmail.com', 
        company_number=8283832, 
        vat_number='GB8283831',
        logo="logo_path",
        invoice_number="123ABC"
    )
    print(db_manager.increment_invoice_number("123ABC"))
    # Add payments for the company
    payment1 = db_manager.add_payment(
        company=company, 
        bank_name='Tide', 
        account_number=8293939, 
        sort_code='22-92-82', 
        bank_address='123 Road, London, GY18 8HV',
        payment_name="Payment 3"
    )

    payment2 = db_manager.add_payment(
        company=company, 
        bank_name='Bank of India', 
        account_number=8293939, 
        sort_code='22-92-82', 
        bank_address='123 Road, London, GY18 8HV',
        payment_name="Payment 1"
    )

    payment3 = db_manager.add_payment(
        company=company, 
        bank_name='HSBC', 
        account_number=8293939, 
        sort_code='22-92-82', 
        bank_address='123 Road, London, GY18 8HV',
        payment_name="Payment 2"
    )