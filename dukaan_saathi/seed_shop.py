import argparse
from getpass import getpass
from .main import create_shop

parser = argparse.ArgumentParser(description="Provision a shop owner and hashed PIN in MongoDB.")
parser.add_argument("--name", required=True)
parser.add_argument("--phone", required=True, help="E.164 or 10-digit Indian mobile number")
args = parser.parse_args()
pin = getpass("Choose a 4–12 digit shop PIN: ")
print(f"Created shop {create_shop(args.name, args.phone, pin)}")
