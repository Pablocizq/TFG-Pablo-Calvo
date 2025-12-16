import requests
import json
import urllib3
from django.db import connection

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CkanClient:
    def __init__(self, user_id=1):
        self.base_url = "https://localhost:8443/api/3/action/"
        self.api_key = self._get_api_token(user_id)

    def _get_api_token(self, user_id):
        with connection.cursor() as cursor:
            cursor.execute("SELECT token_ckan FROM usuario WHERE id_usuario = %s", [user_id])
            row = cursor.fetchone()
            if row:
                return row[0]
        return None

    def _post(self, action, data=None, files=None):
        if not self.api_key:
            raise Exception("No CKAN API Token found for user.")
        
        headers = {'Authorization': self.api_key}
        url = f"{self.base_url}{action}"
        

        try:
            if files:
                response = requests.post(url, data=data, files=files, headers=headers, verify=False)
            else:
                response = requests.post(url, json=data, headers=headers, verify=False)
                
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if hasattr(e.response, 'text'):
                error_msg += f": {e.response.text}"
            raise Exception(f"CKAN API Error: {error_msg}")

    def get_user_organizations(self):

        return self._post("organization_list_for_user", data={"permission": "create_dataset"})

    def create_organization(self, name, description):
        data = {
            "name": name.lower().replace(" ", "-"),
            "title": name,
            "description": description
        }
        return self._post("organization_create", data=data)

    def create_dataset(self, metadata, organization_id):
        data = metadata.copy()
        data['owner_org'] = organization_id
        return self._post("package_create", data=data)

    def update_dataset(self, dataset_id, metadata, organization_id=None):
        data = metadata.copy()
        data['id'] = dataset_id
        if organization_id:
            data['owner_org'] = organization_id
        return self._post("package_update", data=data)
    
    def resource_create(self, dataset_id, file_obj, filename, file_format, description=""):
        data = {
            "package_id": dataset_id,
            "name": filename,
            "format": file_format,
            "description": description
        }
        files = {
            'upload': (filename, file_obj)
        }
        return self._post("resource_create", data=data, files=files)
