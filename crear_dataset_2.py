import requests
import json
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CKAN_URL = "https://localhost:8443"
API_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiItaHk3RVBJLWstRGo3MXBJU1M3QVNvbkNiZGEtTHhlaHA5SG94SERIa3NvIiwiaWF0IjoxNzU5NzYxODEwfQ.fBX5cKznWz_TL3yGD_5sgEjAWxLW3hovDWNmbkywy4U"

dataset_dict = {
    "name": "dataset_prueba_2",
    "title": "Mi Dataset de Prueba 2",
    "notes": "Descripción.",
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

result = response.json()
if not result.get("success"):
    print("❌ Error creando dataset:", result)
    exit()

dataset_id = result["result"]["id"]
print(f"✅ Dataset creado con ID: {dataset_id}")

file_path = r"C:\Users\Pablo\OneDrive\Documentos\PABLO\8O_CUATRIMESTRE\TFG\ckan\ckan-docker\prueba.csv"  # ruta al archivo local

resource_dict = {
    "package_id": dataset_id,
    "name": "CSV",
    "description": "Archivo CSV cargado",
    "format": "CSV"
}

with open(file_path, "rb") as f:
    upload = {"upload": f}
    res = requests.post(
        f"{CKAN_URL}/api/3/action/resource_create",
        headers={"Authorization": API_TOKEN},
        data=resource_dict,
        files=upload,
        verify=False
    )

res_json = res.json()
if res_json.get("success"):
    print("✅ Recurso subido correctamente:")
    print(json.dumps(res_json["result"], indent=2))
else:
    print("⚠️ Error al subir recurso:")
    print(json.dumps(res_json, indent=2))
