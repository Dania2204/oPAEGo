"""Pruebas de desempeño para la evaluación ISO/IEC 25010 (RNF-01, RNF-02, RNF-03).

Instalar y ejecutar (con el servidor y los datos de demostración arriba):

    pip install locust
    locust -f rendimiento/locustfile.py --host http://localhost:8000

Simula conductores que transmiten su ubicación y administradores que
consultan el mapa y los indicadores. Los valores objetivo (tiempo máximo de
respuesta y usuarios simultáneos) son los [COMPLETAR] de la Tabla 5.
"""

import random

from locust import HttpUser, between, task

CLAVE = "Paego2026!"


class _Autenticado(HttpUser):
    abstract = True
    email = ""

    def on_start(self):
        r = self.client.post(
            "/api/auth/token/", json={"email": self.email, "password": CLAVE}, name="login"
        )
        self.client.headers["Authorization"] = "Bearer " + r.json()["access"]


class Conductor(_Autenticado):
    """RNF-02: envío periódico de la ubicación."""

    wait_time = between(10, 15)
    email = "conductor2@paego.local"

    def on_start(self):
        super().on_start()
        envios = self.client.get("/api/envios/?estado=EN_TRANSITO", name="mis envíos").json()
        self.envio = envios["results"][0]["id"] if envios["results"] else None

    @task
    def ubicacion(self):
        if self.envio is None:
            return
        self.client.post(
            f"/api/envios/{self.envio}/ubicaciones/",
            json={
                "latitud": round(1.20 + random.random() / 100, 6),
                "longitud": round(-77.28 + random.random() / 100, 6),
            },
            name="ubicación",
        )


class Administrador(_Autenticado):
    """RF-29 / RF-32: mapa en tiempo real e indicadores."""

    wait_time = between(5, 10)
    email = "admin@paego.local"

    @task(5)
    def mapa(self):
        self.client.get("/api/monitoreo/en-transito/", name="mapa en tránsito")

    @task(2)
    def indicadores(self):
        self.client.get("/api/monitoreo/indicadores/", name="indicadores")

    @task(1)
    def envios(self):
        self.client.get("/api/envios/", name="lista de envíos")
