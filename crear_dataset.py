import requests
import json
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CKAN_URL = "https://localhost:8443"

API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiItaHk3RVBJLWstRGo3MXBJU1M3QVNvbkNiZGEtTHhlaHA5SG94SERIa3NvIiwiaWF0IjoxNzU5NzYxODEwfQ.fBX5cKznWz_TL3yGD_5sgEjAWxLW3hovDWNmbkywy4U"

dataset_dict = {
    "name": "dataset_prueba",
    "title": "Mi Dataset de Prueba",
    "notes": "Descripción",
    "owner_org": "prueba_dataset",
    "author": "Pablo",
    "author_email": "your_email@example.com",
    "license_id": "cc-by",
    "private": True
}

response = requests.post(
    f"{CKAN_URL}/api/3/action/package_create",
    headers={
        "Authorization": API_TOKEN,
        "Content-Type": "application/json"
    },
    data=json.dumps(dataset_dict),
    verify=False
)

if response.status_code == 200:
    result = response.json()
    if result.get("success"):
        print("✅ Dataset creado correctamente:")
        print(json.dumps(result["result"], indent=2))
    else:
        print("⚠️ Error en CKAN:")
        print(result.get("error"))
else:
    print(f"❌ Error HTTP {response.status_code}: {response.text}")
