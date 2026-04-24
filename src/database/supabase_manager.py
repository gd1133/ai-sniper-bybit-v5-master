import base64
import hashlib
import os
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from supabase import Client, create_client
from dotenv import load_dotenv

load_dotenv()


class SupabaseManager:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.crypto_secret = os.getenv("SUPABASE_CLIENTS_SECRET") or self.key
        self.cipher = self._build_cipher()
        self.cloud_enabled = False
        self.cloud_disable_reason = None
        if self.url and self.key:
            self.client: Optional[Client] = create_client(self.url, self.key)
            self.cloud_enabled = True
            print("☁️ Supabase conectado com sucesso!")
        else:
            self.client = None
            print("⚠️ Supabase não configurado no .env")

    def is_available(self) -> bool:
        return self.client is not None and self.cloud_enabled

    def _disable_cloud(self, reason: str):
        if not self.cloud_enabled:
            return
        self.cloud_enabled = False
        self.cloud_disable_reason = reason
        print(f"⚠️ Supabase desativado para esta sessão: {reason}. Fallback local ativo.")

    def _handle_cloud_error(self, action: str, error: Exception):
        message = str(error)
        normalized = message.lower()
        if "pgrst205" in normalized or "could not find the table" in normalized or "schema cache" in normalized:
            self._disable_cloud("tabela ausente ou schema cache inválido")
            return
        print(f"❌ Erro ao {action} no Supabase: {error}")

    def _build_cipher(self) -> Optional[Fernet]:
        if not self.crypto_secret:
            return None
        key_material = hashlib.sha256(str(self.crypto_secret).encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(key_material)
        return Fernet(fernet_key)

    def _encrypt_field(self, value: Any) -> Any:
        if value in [None, ""] or not self.cipher:
            return value
        raw = str(value)
        if raw.startswith("enc::"):
            return raw
        token = self.cipher.encrypt(raw.encode("utf-8")).decode("utf-8")
        return f"enc::{token}"

    def _decrypt_field(self, value: Any) -> Any:
        if value in [None, ""]:
            return value
        raw = str(value)
        if not raw.startswith("enc::"):
            return raw
        if not self.cipher:
            return ""
        token = raw[5:]
        try:
            return self.cipher.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken:
            return ""

    def _protect_client_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        protected = dict(payload or {})
        for field in ("bybit_key", "bybit_secret", "tg_token", "tg_api_key", "chat_id"):
            protected[field] = self._encrypt_field(protected.get(field))
        return protected

    def _prepare_client_payload(self, client: Dict[str, Any]) -> Dict[str, Any]:
        payload = {
            "nome": client.get("nome"),
            "bybit_key": client.get("bybit_key"),
            "bybit_secret": client.get("bybit_secret"),
            "tg_token": client.get("tg_token"),
            "tg_api_key": client.get("tg_api_key"),
            "chat_id": client.get("chat_id"),
            "status": client.get("status", "ativo"),
            "saldo_base": float(client.get("saldo_base", 1000.0) or 1000.0),
            "is_testnet": bool(client.get("is_testnet", True)),
            "balance_source": client.get("balance_source", "form_test_balance"),
        }
        client_id = client.get("id")
        if client_id is not None:
            payload["id"] = int(client_id)
        return self._protect_client_payload(payload)

    def _normalize_client_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(row or {})
        for field in ("bybit_key", "bybit_secret", "tg_token", "tg_api_key", "chat_id"):
            normalized[field] = self._decrypt_field(normalized.get(field))
        if "saldo_base" in normalized:
            try:
                normalized["saldo_base"] = float(normalized.get("saldo_base") or 0)
            except Exception:
                normalized["saldo_base"] = 0.0
        if "is_testnet" in normalized:
            value = normalized.get("is_testnet")
            normalized["is_testnet"] = 1 if value in [True, 1, "1", "true", "TRUE"] else 0
        if "balance_source" not in normalized:
            normalized["balance_source"] = "form_test_balance"
        return normalized

    def get_clients(self, active_only: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Lê clientes do Supabase. Retorna None apenas quando a nuvem está indisponível."""
        if not self.is_available():
            return None

        try:
            query = self.client.table("clientes").select("*").order("id", desc=True)
            if active_only:
                query = query.eq("status", "ativo")
            result = query.execute()
            rows = getattr(result, "data", None)
            if rows is None:
                return []
            return [self._normalize_client_row(row) for row in rows]
        except Exception as e:
            self._handle_cloud_error("buscar clientes", e)
            return None

    def get_client_by_id(self, client_id: int) -> Optional[Dict[str, Any]]:
        """Busca um cliente específico no Supabase."""
        if not self.is_available():
            return None

        try:
            result = self.client.table("clientes").select("*").eq("id", int(client_id)).limit(1).execute()
            rows = getattr(result, "data", None) or []
            if not rows:
                return None
            return self._normalize_client_row(rows[0])
        except Exception as e:
            self._handle_cloud_error(f"buscar cliente {client_id}", e)
            return None

    def save_client(self, client_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Cria ou atualiza um cliente no Supabase e devolve a linha persistida."""
        if not self.is_available():
            return None

        payload = self._prepare_client_payload(client_data)

        try:
            table = self.client.table("clientes")
            if payload.get("id") is None:
                result = table.insert(payload).execute()
            else:
                result = table.upsert(payload).execute()

            rows = getattr(result, "data", None) or []
            if rows:
                return self._normalize_client_row(rows[0])

            if payload.get("id") is not None:
                return self.get_client_by_id(int(payload["id"]))

            latest = self.get_clients(active_only=False)
            if latest:
                return latest[0]
            return payload
        except Exception as e:
            self._handle_cloud_error("salvar cliente", e)
            return None

    def delete_client(self, client_id: int) -> bool:
        """Remove um cliente do Supabase."""
        if not self.is_available():
            return False

        try:
            self.client.table("clientes").delete().eq("id", int(client_id)).execute()
            return True
        except Exception as e:
            self._handle_cloud_error(f"deletar cliente {client_id}", e)
            return False

    def sync_clients(self, local_db_manager):
        """Sincroniza clientes locais para o Supabase."""
        if not self.is_available():
            return

        clients = local_db_manager.get_all_clients()
        for client in clients:
            if not self.is_available():
                break
            self.save_client(client)
        print("✅ Sincronização em background finalizada.")

    def record_trade(self, trade_data):
        """Registra um trade diretamente no Supabase."""
        if not self.is_available():
            return
        try:
            self.client.table("trades").insert(trade_data).execute()
        except Exception as e:
            self._handle_cloud_error("registrar trade", e)

    def close_open_trades_by_symbol(self, symbol: str, current_price: float, closed_at: str, note_suffix: str = "MANUAL_CLOSE") -> int:
        """Fecha trades open no Supabase por símbolo, quando houver sincronização cloud."""
        if not self.is_available():
            return 0

        try:
            result = self.client.table("trades").select("*").eq("pair", symbol).eq("status", "open").execute()
            rows = getattr(result, "data", None) or []
            closed = 0

            for row in rows:
                try:
                    entry_price = float(row.get("entry_price") or 0)
                    margin = float(row.get("profit") or 0)
                    side = str(row.get("side") or "").upper()
                    if entry_price <= 0 or margin <= 0 or current_price <= 0:
                        pnl_pct = 0.0
                        profit_value = 0.0
                    else:
                        is_sell = side in {"VENDER", "SELL"}
                        pnl_pct = ((entry_price - current_price) / entry_price) * 100 if is_sell else ((current_price - entry_price) / entry_price) * 100
                        profit_value = round(margin * (pnl_pct / 100), 2)

                    notes = f"{str(row.get('notes') or '').strip()} | {note_suffix} @ {float(current_price):.8f}".strip()
                    self.client.table("trades").update({
                        "pnl_pct": round(float(pnl_pct), 4),
                        "profit": profit_value,
                        "closed_at": closed_at,
                        "notes": notes,
                        "status": "closed",
                    }).eq("id", row.get("id")).execute()
                    closed += 1
                except Exception:
                    continue

            return closed
        except Exception as e:
            self._handle_cloud_error(f"fechar trades open de {symbol}", e)
            return 0
