import os
import replicate

# Load Replicate API token from environment variable
replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
if not replicate_api_token:
    print("REPLICATE_API_TOKEN environment variable not set. Please set it before running this script.")
    exit(0)

os.environ["REPLICATE_API_TOKEN"] = replicate_api_token

try:
    model = replicate.models.get("lucataco/florence-2-large")
    print("Latest version for florence-2-large:", model.latest_version.id)
except Exception as e:
    print(e)
try:
    model = replicate.models.get("lucataco/florence-2-base")
    print("Latest version for florence-2-base:", model.latest_version.id)
except Exception as e:
    print(e)
