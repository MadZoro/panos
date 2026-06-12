import os
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

class SupabaseClient:
    def __init__(self):
        self.url = SUPABASE_URL
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
    
    def get_products(self):
        response = requests.get(
            f"{self.url}/rest/v1/products?select=*",
            headers=self.headers
        )
        return response.json()
    
    def get_product_by_id(self, product_id):
        response = requests.get(
            f"{self.url}/rest/v1/products?id=eq.{product_id}&select=*",
            headers=self.headers
        )
        data = response.json()
        return data[0] if data else None
    
    def register_user(self, user_id, username, ip_address):
        # Проверяем, существует ли пользователь
        check = requests.get(
            f"{self.url}/rest/v1/users?user_id=eq.{user_id}",
            headers=self.headers
        )
        if check.json():
            return True
        
        # Создаём пользователя
        response = requests.post(
            f"{self.url}/rest/v1/users",
            headers=self.headers,
            json={
                "user_id": user_id,
                "username": username,
                "ip_address": ip_address
            }
        )
        return response.status_code == 201
    
    def activate_key(self, key_code, user_id):
        response = requests.post(
            f"{self.url}/rest/v1/rpc/activate_key",
            headers=self.headers,
            json={
                "p_key_code": key_code,
                "p_user_id": user_id
            }
        )
        return response.json()
