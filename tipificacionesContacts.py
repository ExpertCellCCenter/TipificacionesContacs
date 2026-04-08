import time as pytime
from datetime import date, datetime, timedelta
from io import BytesIO
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.express as px
import pyodbc
import requests
import streamlit as st


# -------------------------------
# CONFIG
# -------------------------------
st.set_page_config(
    page_title="CC2 + JV - Tipificación diaria",
    page_icon="📞",
    layout="wide",
)

st.markdown(
    """
    <style>
    .pbix-band {
        background: #0b6a8f;
        color: #ffffff;
        text-align: center;
        font-weight: 800;
        font-size: 1.05rem;
        border-radius: 0;
        padding: 0.55rem 0.8rem;
        margin: 0.4rem 0 0.8rem 0;
        letter-spacing: 0.01em;
    }

    .pbix-legend {
        color: rgba(255,255,255,0.84);
        text-align: center;
        font-size: 0.95rem;
        margin: 0.15rem 0 1.15rem 0;
        line-height: 1.35;
    }

    .pbix-center-page-title {
        color: #52b7ea;
        font-size: 1.9rem;
        font-style: italic;
        font-weight: 500;
        margin: 1.1rem 0 0.55rem 0;
        line-height: 1.1;
    }

    .mini-band {
        background: #0b6a8f;
        color: #ffffff;
        text-align: center;
        font-weight: 800;
        font-size: 0.98rem;
        padding: 0.45rem 0.8rem;
        margin: 0.3rem 0 0.85rem 0;
    }

    .metric-pack-title {
        font-size: 1.15rem;
        font-weight: 700;
        margin: 0.15rem 0 0.55rem 0;
        color: #f5f7fb;
    }

    .metric-pack-scope {
        color: rgba(255,255,255,0.62);
        margin-top: 0;
        margin-bottom: 0.75rem;
        font-size: 0.90rem;
        line-height: 1.35;
    }

    .metric-card {
        background: linear-gradient(180deg, rgba(22,27,34,0.96), rgba(13,17,23,0.96));
        border: 1px solid rgba(255,255,255,0.08);
        border-left: 4px solid var(--accent, #ff4b4b);
        border-radius: 16px;
        padding: 16px 18px;
        min-height: 110px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.28);
        margin-bottom: 12px;
    }

    .metric-card:hover {
        transform: translateY(-1px);
        box-shadow: 0 12px 28px rgba(0,0,0,0.32);
        transition: 0.18s ease;
    }

    .metric-label {
        font-size: 0.92rem;
        font-weight: 600;
        color: rgba(255,255,255,0.78);
        margin-bottom: 10px;
        line-height: 1.25;
    }

    .metric-value {
        font-size: 2.2rem;
        font-weight: 800;
        color: #ffffff;
        line-height: 1.05;
        letter-spacing: -0.02em;
    }

    .section-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #f5f7fb;
        margin: 1.0rem 0 0.2rem 0;
        line-height: 1.1;
    }

    .section-subtitle {
        color: rgba(255,255,255,0.82);
        font-size: 0.96rem;
        margin-bottom: 0.8rem;
        line-height: 1.35;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# -------------------------------
# CONSTANTS
# -------------------------------
API_URL = "https://eva.bonsaif.com/api"
CDMX_TZ = ZoneInfo("America/Mexico_City")

TARGET_COLS = [
    "ID_CC", "Campaña_CC", "Cliente_CC", "Tel_Marcado_CC", "Carrier_CC", "Tipo_Tel_CC",
    "Duracion_CC", "Duracion_Min_CC", "Estatus_CC", "Codigo_Accion_CC", "Codigo_Resultado_CC",
    "Fecha_CC", "Codigo_sip_CC", "Descripcion_sip_CC", "Grabacion_CC", "Extension_CC", "Gestor_CC",
    "Obs_CC", "Origen_CC", "Colgo_Agente_CC", "Salida_CC", "Campo_Clave", "acw",
    "Calificacion_Int_CC", "Sistema"
]

TIP_ORDER_3 = ["CONTACTO", "IMPROCEDENTE", "NO CONTACTADO", "OTROS / SIN CALIFICACION"]
TIP_ABBR = {
    "CONTACTO": "CTO",
    "IMPROCEDENTE": "IMP",
    "NO CONTACTADO": "NCT",
    "OTROS / SIN CALIFICACION": "OTR"
}

BAD_RECORD_RULE = {
    "ID_CC": 7284,
    "Campaña_CC": "CC2-NOVW3-18000R",
    "Cliente_CC": "CCENTER2-EXPERTCELL",
    "Tel_Marcado_CC": "5585327633",
}

JV_SUPERVISOR_DISPLAY_MAP = {
    "MARIA FERNANDA": "MARIA FERNANDA MARTINEZ BISTRAIN",
    "JORGE MIGUEL": "JORGE MIGUEL URENA ZARATE",
    "MARIA LUISA": "MARIA LUISA",
}

PBIX_JV_DISPLAY_SUPERVISORS = set(JV_SUPERVISOR_DISPLAY_MAP.values())

PBIX_CC2_DISPLAY_SUPERVISORS = {
    "ALAN UZIEL SALAZAR AGUILAR",
    "ALFREDO CABRERA PADRON",
    "CARLOS ALBERTO AGUILAR CANO",
    "REYNA LIZZETTE MARTINEZ GARCIA",
}

CC2_SPECIAL_BUCKETS = {
    "ENCUBADORA",
    "SIN SUPERVISOR",
    "SIN STAFF",
}

CC2_ALLOWED_DISPLAY = PBIX_CC2_DISPLAY_SUPERVISORS | CC2_SPECIAL_BUCKETS


# -------------------------------
# SECRETS
# -------------------------------
def get_secret(section: str, key: str, default: str = "") -> str:
    try:
        return str(st.secrets[section][key]).strip()
    except Exception:
        return default


JV_API_KEY = get_secret("bonsaif", "jv_api_key")
JV_SYS = get_secret("bonsaif", "jv_sys", "cc61")

CC2_API_KEY = get_secret("bonsaif", "cc2_api_key")
CC2_SYS = get_secret("bonsaif", "cc2_sys", "cc62")

SQL_HOST = get_secret("sqlserver", "host")
SQL_DATABASE = get_secret("sqlserver", "database")
SQL_USERNAME = get_secret("sqlserver", "username")
SQL_PASSWORD = get_secret("sqlserver", "password")
SQL_DRIVER = get_secret("sqlserver", "driver", "ODBC Driver 18 for SQL Server")


# -------------------------------
# HELPERS
# -------------------------------
def mexico_now() -> datetime:
    return datetime.now(CDMX_TZ)


def to_clean_text(x) -> str:
    if pd.isna(x):
        return ""
    return str(x).strip()


def normalize_status(x) -> str:
    t = to_clean_text(x).upper()
    return "SIN CALIFICACION" if t == "" else t


def status_group_3(status: str) -> str:
    s = normalize_status(status)
    if s in {"CONTACTO", "IMPROCEDENTE", "NO CONTACTADO"}:
        return s
    return "OTROS / SIN CALIFICACION"


def ensure_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    return out[cols]


def compute_business_reference_day(today: date) -> date:
    ayer1 = today - timedelta(days=1)

    is_dec26 = today.month == 12 and today.day == 26
    is_jan2 = today.month == 1 and today.day == 2
    is_feb2 = today.month == 2 and today.day == 2
    is_feb3 = today.month == 2 and today.day == 3
    is_mar16 = today.month == 3 and today.day == 16
    is_mar17 = today.month == 3 and today.day == 17

    if is_dec26:
        return date(today.year, 12, 24)
    elif is_jan2:
        return date(today.year - 1, 12, 31)
    elif is_feb3:
        return today - timedelta(days=3)
    elif is_feb2:
        return today - timedelta(days=1)
    elif is_mar16:
        return today - timedelta(days=2)
    elif is_mar17:
        return today - timedelta(days=3)
    elif ayer1.weekday() == 6:
        return today - timedelta(days=2)
    else:
        return ayer1


def clean_name(t):
    if pd.isna(t):
        return None

    s = str(t).strip().upper()
    s = (
        s.replace("Á", "A")
         .replace("É", "E")
         .replace("Í", "I")
         .replace("Ó", "O")
         .replace("Ú", "U")
         .replace("Ñ", "N")
         .replace(".", " ")
         .replace(",", " ")
         .replace("/", " ")
         .replace("-", " ")
    )
    s = s.replace("JAIR DALL", "JAIR DALI")
    s = " ".join([p for p in s.split(" ") if p != ""])
    return s


def canonical_supervisor_name(supervisor_raw):
    sup = clean_name(supervisor_raw)

    if sup is None or sup == "":
        return "SIN SUPERVISOR"

    if sup in {"JV", "CC61"}:
        return "SIN SUPERVISOR JV"
    if sup in {"CC2", "CC62"}:
        return "SIN SUPERVISOR"
    if "ENCUBADORA" in sup:
        return "ENCUBADORA"
    if "SIN STAFF" in sup:
        return "SIN STAFF"
    if "SIN SUPERVISOR" in sup:
        return "SIN SUPERVISOR"

    # JV
    if (
        "JORGE MIGUEL" in sup
        or sup in {"JORGE", "J MIGUEL", "JORGE MIGUEL URENA ZARATE"}
    ):
        return "JORGE MIGUEL"

    if (
        "MARIA FERNANDA" in sup
        or sup in {"FERNANDA", "MARIA FERNANADA", "MARIA FERNANDA MARTINEZ BISTRAIN"}
    ):
        return "MARIA FERNANDA"

    if (
        "MARIA LUISA" in sup
        or sup in {"LUISA", "MARIA LUIZA", "MARIA LUISA"}
    ):
        return "MARIA LUISA"

    # CC2
    if "REYNA" in sup:
        return "REYNA LIZZETTE MARTINEZ GARCIA"

    if "ALFREDO" in sup:
        return "ALFREDO CABRERA PADRON"

    if "ALAN UZIEL" in sup or ("ALAN" in sup and "SALAZAR" in sup):
        return "ALAN UZIEL SALAZAR AGUILAR"

    if (
        sup == "CARLOS"
        or "CARLOS ALBERTO" in sup
        or ("CARLOS" in sup and "AGUILAR" in sup)
    ):
        return "CARLOS ALBERTO AGUILAR CANO"

    return sup


def normalize_supervisor_display(centro, supervisor_raw):
    centro = to_clean_text(centro).upper()
    sup = canonical_supervisor_name(supervisor_raw)

    if sup is None or sup == "":
        return "SIN SUPERVISOR"

    if centro == "JV":
        if sup in JV_SUPERVISOR_DISPLAY_MAP:
            return JV_SUPERVISOR_DISPLAY_MAP[sup]
        return "SIN SUPERVISOR JV"

    if centro == "CC2":
        if sup in CC2_ALLOWED_DISPLAY:
            return sup
        return "SIN SUPERVISOR"

    return sup


def add_supervisor_display(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if "Centro" not in out.columns:
        out["Centro"] = ""
    if "Calificacion_Int_CC" not in out.columns:
        out["Calificacion_Int_CC"] = ""

    out["Supervisor_Display"] = [
        normalize_supervisor_display(c, s)
        for c, s in zip(out["Centro"], out["Calificacion_Int_CC"])
    ]

    return out


def apply_powerbi_center_page_scope(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    out = add_supervisor_display(df.copy())

    out["Centro"] = out["Centro"].fillna("").astype(str).str.strip().str.upper()
    out["Cliente_CC_UP"] = out["Cliente_CC"].fillna("").astype(str).str.strip().str.upper()
    out["Gestor_CC_CLEAN_TMP"] = out["Gestor_CC"].map(clean_name)

    sup = get_supervisores_cc2()
    active_cc2_agents = set()
    if not sup.empty and "Gestor_CC_CLEAN" in sup.columns:
        active_cc2_agents = set(sup["Gestor_CC_CLEAN"].dropna().astype(str).tolist())

    jv = out[
        (out["Centro"] == "JV") &
        (out["Cliente_CC_UP"] == "EXPERT CELL") &
        (out["Supervisor_Display"].isin(PBIX_JV_DISPLAY_SUPERVISORS))
    ].copy()

    cc2 = out[
        (out["Centro"] == "CC2") &
        (out["Cliente_CC_UP"] == "CCENTER2-EXPERTCELL") &
        (out["Supervisor_Display"].isin(PBIX_CC2_DISPLAY_SUPERVISORS))
    ].copy()

    if active_cc2_agents:
        cc2 = cc2[cc2["Gestor_CC_CLEAN_TMP"].isin(active_cc2_agents)].copy()

    final = pd.concat([jv, cc2], ignore_index=True)

    return final.drop(columns=["Cliente_CC_UP", "Gestor_CC_CLEAN_TMP"], errors="ignore")


def map_sistema_to_centro(x) -> str:
    s = to_clean_text(x).upper()
    if s == "CC61":
        return "JV"
    if s == "CC62":
        return "CC2"
    return s if s else "N/A"


def infer_center_from_supervisor(supervisor_raw, sistema_raw=None) -> str:
    sup = canonical_supervisor_name(supervisor_raw)

    if sup in {"MARIA FERNANDA", "MARIA LUISA", "JORGE MIGUEL", "SIN SUPERVISOR JV"}:
        return "JV"

    if sup in CC2_ALLOWED_DISPLAY or sup == "SIN SUPERVISOR":
        return "CC2"

    fallback = map_sistema_to_centro(sistema_raw)
    return fallback if fallback in {"JV", "CC2"} else "N/A"


def build_detail_rename_map(team_col: str, agent_col: str) -> dict:
    rename_map = {
        "Centro": "Centro",
        "Sistema": "Sistema",
        team_col: "Supervisor",
        agent_col: "Agente",
        "Tipificacion_3": "Tipificación general",
        "Tipificacion_Detalle": "Tipificación detalle",
        "Tel_Marcado_CC": "Teléfono",
        "Campaña_CC": "Campaña",
        "Cliente_CC": "Cliente",
        "Duracion_CC": "Duración (seg)",
        "Duracion_Min_CC": "Duración (min)",
        "Codigo_Accion_CC": "Código acción",
        "Codigo_Resultado_CC": "Código resultado",
        "Extension_CC": "Extensión",
        "Descripcion_sip_CC": "Descripción SIP",
        "Campo_Clave": "Campo clave",
        "Grabacion_CC": "Grabación",
        "Fecha_CC": "Fecha",
    }

    if team_col != "Calificacion_Int_CC":
        rename_map["Calificacion_Int_CC"] = "Supervisor original"

    if agent_col != "Extension_CC":
        rename_map["Extension_CC"] = "Extensión"

    return rename_map


# -------------------------------
# SQL - SUPERVISORES CC2
# -------------------------------
def build_sql_connection_string() -> str:
    return (
        f"DRIVER={{{SQL_DRIVER}}};"
        f"SERVER={SQL_HOST};"
        f"DATABASE={SQL_DATABASE};"
        f"UID={SQL_USERNAME};"
        f"PWD={SQL_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def get_supervisores_cc2() -> pd.DataFrame:
    cols = ["Clave_int_agente", "Gestor_CC"]

    if not SQL_HOST or not SQL_DATABASE or not SQL_USERNAME or not SQL_PASSWORD:
        return pd.DataFrame(columns=cols)

    query = """
    SELECT DISTINCT
        e.[Jefe Inmediato]  AS Clave_int_agente,
        e.[Nombre Completo] AS Gestor_CC
    FROM
        reporte_empleado('EMPRESA_MAESTRA',1,'','') AS e
    WHERE
        [Canal de Venta] = 'ATT'
        AND [Operacion]   = 'CONTACT CENTER'
        AND [Tipo Tienda] = 'VIRTUAL'
        AND [Puesto] IN (
            'ASESOR TELEFONICO',
            'ASESOR TELEFONICO 7500',
            'EJECUTIVO TELEFONICO 6500 AM',
            'EJECUTIVO TELEFONICO 6500 PM',
            'SUPERVISOR DE CONTACT CENTER'
        )
        AND Estatus = 'ACTIVO'
    """

    conn = pyodbc.connect(build_sql_connection_string(), timeout=45)
    try:
        df = pd.read_sql(query, conn)
    finally:
        conn.close()

    for c in cols:
        if c not in df.columns:
            df[c] = np.nan

    df = df[cols].copy()
    df["Clave_int_agente"] = df["Clave_int_agente"].fillna("").astype(str).str.strip()
    df["Gestor_CC"] = df["Gestor_CC"].fillna("").astype(str).str.strip()

    df["Clave_int_agente"] = np.where(
        df["Clave_int_agente"] == "",
        "ENCUBADORA",
        df["Clave_int_agente"]
    )

    df["Gestor_CC_CLEAN"] = df["Gestor_CC"].map(clean_name)

    return df


# -------------------------------
# API FETCHERS
# -------------------------------
def fetch_api_records(params: dict) -> list[dict]:
    response = requests.get(API_URL, params=params, timeout=45)
    response.raise_for_status()
    payload = response.json()
    result = payload.get("result", [])
    if isinstance(result, list):
        return result
    return []


def normalize_api_df(records: list[dict]) -> pd.DataFrame:
    cols = [
        "ID_CC", "Campaña_CC", "Cliente_CC", "Tel_Marcado_CC", "Carrier_CC", "Tipo_Tel_CC",
        "Duracion_CC", "Duracion_Min_CC", "Estatus_CC", "Codigo_Accion_CC", "Codigo_Resultado_CC",
        "Fecha_CC", "Codigo_sip_CC", "Descripcion_sip_CC", "Grabacion_CC", "Extension_CC", "Gestor_CC",
        "Obs_CC", "Origen_CC", "Colgo_Agente_CC", "Salida_CC", "Campo_Clave", "acw",
        "Calificacion_Int_CC", "Clave_int_cli", "Calificacion_Int_CC_Final"
    ]

    if not records:
        return pd.DataFrame(columns=cols)

    df = pd.DataFrame(records)
    for c in cols:
        if c not in df.columns:
            df[c] = np.nan

    df = df[cols].copy()

    text_cols = [
        "Campaña_CC", "Cliente_CC", "Tel_Marcado_CC", "Carrier_CC", "Tipo_Tel_CC",
        "Estatus_CC", "Codigo_Accion_CC", "Codigo_Resultado_CC", "Codigo_sip_CC",
        "Descripcion_sip_CC", "Grabacion_CC", "Extension_CC", "Gestor_CC",
        "Obs_CC", "Colgo_Agente_CC", "Salida_CC", "Calificacion_Int_CC",
        "Clave_int_cli", "Calificacion_Int_CC_Final"
    ]
    num_cols = ["ID_CC", "Duracion_CC", "Duracion_Min_CC", "Origen_CC", "Campo_Clave", "acw"]

    for c in text_cols:
        df[c] = df[c].astype("string")

    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["Fecha_CC"] = pd.to_datetime(df["Fecha_CC"], errors="coerce")

    nuevo = df["Clave_int_cli"].fillna("").astype(str).str.strip()
    viejo = df["Calificacion_Int_CC"].fillna("").astype(str).str.strip()

    df["Calificacion_Int_CC"] = np.where(
        nuevo != "",
        nuevo,
        np.where(viejo != "", viejo, np.nan)
    )

    df = df.drop(columns=["Clave_int_cli"])
    return df


def fetch_jv_raw(pdate: date) -> pd.DataFrame:
    if not JV_API_KEY or not JV_SYS:
        return pd.DataFrame()

    pdate_text = pdate.strftime("%Y-%m-%d")
    params = {
        "service": "cc/api",
        "m": "27",
        "key": JV_API_KEY,
        "sys": JV_SYS,
        "fecha_ini": pdate_text,
        "fecha_fin": pdate_text,
    }

    for attempt in range(3):
        try:
            records = fetch_api_records(params)
            return normalize_api_df(records)
        except Exception:
            pytime.sleep(1 + attempt)

    return pd.DataFrame()


def fetch_cc2_raw(pdate: date) -> pd.DataFrame:
    if not CC2_API_KEY or not CC2_SYS:
        return pd.DataFrame()

    pdate_text = pdate.strftime("%Y-%m-%d")

    params_primary = {
        "service": "cc/api",
        "m": "27",
        "key": CC2_API_KEY,
        "sys": CC2_SYS,
        "fechaini": pdate_text,
        "fechafin": pdate_text,
    }

    params_fallback = {
        "service": "cc/api",
        "m": "27",
        "key": CC2_API_KEY,
        "sys": CC2_SYS,
        "fecha_ini": pdate_text,
        "fecha_fin": pdate_text,
    }

    for attempt in range(3):
        try:
            records = fetch_api_records(params_primary)
            if not records:
                records = fetch_api_records(params_fallback)
            return normalize_api_df(records)
        except Exception:
            pytime.sleep(1 + attempt)

    return pd.DataFrame()


# -------------------------------
# SOURCE PREP
# -------------------------------
def prepare_jv_for_date(pdate: date) -> pd.DataFrame:
    return fetch_jv_raw(pdate).copy()


def prepare_cc2_for_date(pdate: date) -> pd.DataFrame:
    raw = fetch_cc2_raw(pdate)

    if raw.empty:
        return raw.copy()

    out = raw.copy()
    out["Gestor_CC"] = out["Gestor_CC"].map(clean_name)

    sup = get_supervisores_cc2()

    if not sup.empty:
        merged = out.merge(
            sup[["Gestor_CC_CLEAN", "Clave_int_agente"]],
            left_on="Gestor_CC",
            right_on="Gestor_CC_CLEAN",
            how="left"
        )

        supervisor_excel = merged["Clave_int_agente"]
        api_value = merged["Calificacion_Int_CC"]

        merged["Calificacion_Int_CC_Final"] = np.where(
            supervisor_excel.fillna("").astype(str).str.strip() != "",
            supervisor_excel.astype(str),
            np.where(
                api_value.fillna("").astype(str).str.strip() != "",
                api_value.astype(str),
                np.nan
            )
        )

        merged = merged.drop(columns=["Gestor_CC_CLEAN", "Clave_int_agente"])
        out = merged
    else:
        out["Calificacion_Int_CC_Final"] = np.where(
            out["Calificacion_Int_CC"].fillna("").astype(str).str.strip() != "",
            out["Calificacion_Int_CC"].astype(str),
            np.nan
        )

    return out.copy()


# -------------------------------
# CONSOLIDADO_AYER EXACT LOGIC
# -------------------------------
def build_consolidado_exact(jv_df: pd.DataFrame, cc2_df: pd.DataFrame) -> pd.DataFrame:
    jv = jv_df.copy()
    jv["Sistema"] = "CC61"

    cc2 = cc2_df.copy()
    cc2["Sistema"] = "CC62"

    if "Calificacion_Int_CC" in cc2.columns:
        cc2 = cc2.drop(columns=["Calificacion_Int_CC"])

    if "Calificacion_Int_CC_Final" in cc2.columns:
        cc2 = cc2.rename(columns={"Calificacion_Int_CC_Final": "Calificacion_Int_CC"})

    jv2 = ensure_columns(jv, TARGET_COLS)
    cc22 = ensure_columns(cc2, TARGET_COLS)

    combined = pd.concat([jv2, cc22], ignore_index=True)

    combined["Estatus_CC"] = combined["Estatus_CC"].apply(
        lambda x: "SIN CALIFICACION" if str(x).strip() == "" or pd.isna(x) else x
    )

    id_cc = pd.to_numeric(combined.get("ID_CC"), errors="coerce")
    camp = combined.get("Campaña_CC", pd.Series(index=combined.index, dtype="object")).fillna("").astype(str)
    cliente = combined.get("Cliente_CC", pd.Series(index=combined.index, dtype="object")).fillna("").astype(str)
    tel = combined.get("Tel_Marcado_CC", pd.Series(index=combined.index, dtype="object")).fillna("").astype(str)

    mask_bad = (
        id_cc.eq(BAD_RECORD_RULE["ID_CC"]) &
        camp.eq(BAD_RECORD_RULE["Campaña_CC"]) &
        cliente.eq(BAD_RECORD_RULE["Cliente_CC"]) &
        tel.eq(BAD_RECORD_RULE["Tel_Marcado_CC"])
    )
    combined = combined[~mask_bad].copy()

    combined["Campo_Clave"] = pd.to_numeric(combined["Campo_Clave"], errors="coerce")

    combined["_SysOrder"] = np.where(
        combined["Sistema"].fillna("").astype(str).eq("CC62"),
        1,
        0
    )

    combined = combined.sort_values(
        by=["Tel_Marcado_CC", "Fecha_CC", "_SysOrder"],
        ascending=[True, False, False],
        kind="mergesort",
        na_position="last"
    )

    combined = combined.drop_duplicates(subset=["Tel_Marcado_CC"], keep="first").copy()
    combined = combined.drop(columns=["_SysOrder"])

    combined["Centro"] = [
        infer_center_from_supervisor(sup, sis)
        for sup, sis in zip(combined["Calificacion_Int_CC"], combined["Sistema"])
    ]
    combined["Tipificacion_Detalle"] = combined["Estatus_CC"].apply(normalize_status)
    combined["Tipificacion_3"] = combined["Estatus_CC"].apply(status_group_3)
    combined["Tipificacion_3_Abbr"] = combined["Tipificacion_3"].map(TIP_ABBR).fillna("OTR")

    for c in ["Gestor_CC", "Calificacion_Int_CC", "Extension_CC"]:
        if c in combined.columns:
            combined[c] = combined[c].fillna("").astype(str).str.strip()

    return combined.reset_index(drop=True)


# -------------------------------
# CONSOLIDADO BUILDERS
# -------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def get_consolidado_ayer() -> tuple[pd.DataFrame, date]:
    hoy = mexico_now().date()
    target = compute_business_reference_day(hoy)
    alt = target - timedelta(days=1)

    jv_raw0 = fetch_jv_raw(target)
    cc2_raw0 = fetch_cc2_raw(target)

    jv = prepare_jv_for_date(alt if jv_raw0.empty else target)
    cc2 = prepare_cc2_for_date(alt if cc2_raw0.empty else target)

    combined = build_consolidado_exact(jv, cc2)
    return combined, target


@st.cache_data(ttl=60, show_spinner=False)
def get_consolidado_hoy() -> tuple[pd.DataFrame, date]:
    hoy = mexico_now().date()

    jv = prepare_jv_for_date(hoy)
    cc2 = prepare_cc2_for_date(hoy)

    combined = build_consolidado_exact(jv, cc2)
    return combined, hoy


@st.cache_data(ttl=60, show_spinner=False)
def get_consolidado_exact_day(pdate: date) -> pd.DataFrame:
    jv = prepare_jv_for_date(pdate)
    cc2 = prepare_cc2_for_date(pdate)

    combined = build_consolidado_exact(jv, cc2)
    return combined


# -------------------------------
# KPI HELPERS
# -------------------------------
def avg_active_seconds_by_tip(df: pd.DataFrame, tip: str) -> float:
    if df.empty or "Duracion_CC" not in df.columns:
        return 0.0

    s = pd.to_numeric(
        df.loc[df["Tipificacion_3"] == tip, "Duracion_CC"],
        errors="coerce"
    ).dropna()

    s = s[s > 0]

    if s.empty:
        return 0.0

    return float(s.mean())


def calc_agent_hangup_pct(df: pd.DataFrame) -> float:
    if df.empty or "Estatus_CC" not in df.columns or "Colgo_Agente_CC" not in df.columns:
        return 0.0

    status = df["Estatus_CC"].fillna("").astype(str).str.strip().str.upper()
    colgo = df["Colgo_Agente_CC"].fillna("").astype(str).str.strip().str.upper()

    llamadas = int(status.eq("CONTACTO").sum())
    if llamadas == 0:
        return 0.0

    colgar = int((status.eq("CONTACTO") & colgo.eq("SI")).sum())
    return float((colgar / llamadas) * 100)


def calc_discard_block_count(df: pd.DataFrame) -> int:
    if df.empty or "Duracion_CC" not in df.columns:
        return 0

    dur = pd.to_numeric(df["Duracion_CC"], errors="coerce")
    return int(dur.eq(0).sum())


def calc_awc(df: pd.DataFrame) -> int:
    if df.empty or "acw" not in df.columns:
        return 0

    s = pd.to_numeric(df["acw"], errors="coerce").dropna()
    if s.empty:
        return 0

    return int(round(s.mean()))


def compute_metric_pack(df: pd.DataFrame) -> dict:
    return {
        "Contacto (avg sec)": avg_active_seconds_by_tip(df, "CONTACTO"),
        "Improcedente (avg sec)": avg_active_seconds_by_tip(df, "IMPROCEDENTE"),
        "No contactado (avg sec)": avg_active_seconds_by_tip(df, "NO CONTACTADO"),
        "% Colgó Agente": calc_agent_hangup_pct(df),
        "Bloqueo de Discard": calc_discard_block_count(df),
        "AWC": calc_awc(df),
    }


def fmt_metric_value(label: str, value) -> str:
    if "%" in label:
        return f"{float(value):.0f}%"

    if (
        "Bloqueo" in label
        or label == "AWC"
        or "Registros" in label
        or "Total" in label
        or "Otros" in label
    ):
        try:
            return f"{int(round(float(value))):,}"
        except Exception:
            return str(value)

    try:
        return f"{float(value):,.1f}"
    except Exception:
        return str(value)


def render_pbix_band(title: str):
    st.markdown(f'<div class="pbix-band">{title}</div>', unsafe_allow_html=True)


def render_pbix_legend():
    st.markdown(
        '<div class="pbix-legend">CTO = CONTACTO &nbsp;&nbsp;&nbsp; IMP = IMPROCEDENTE &nbsp;&nbsp;&nbsp; NCT = NO CONTACTADO &nbsp;&nbsp;&nbsp; AWC = TIEMPO P/ TIPIFICAR</div>',
        unsafe_allow_html=True
    )


def render_center_page_title(title: str):
    st.markdown(f'<div class="pbix-center-page-title">{title}</div>', unsafe_allow_html=True)


def render_metric_card(label: str, value, accent: str = "#ff4b4b", display_label: str | None = None):
    label_show = display_label if display_label is not None else label

    st.markdown(
        f"""
        <div class="metric-card" style="--accent:{accent}">
            <div class="metric-label">{label_show}</div>
            <div class="metric-value">{fmt_metric_value(label, value)}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_metric_pack(
    title: str,
    pack: dict,
    accent: str = "#ff4b4b",
    subtitle: str = "",
    row1_header: str = "",
    row2_header: str = ""
):
    st.markdown(f'<div class="metric-pack-title">{title}</div>', unsafe_allow_html=True)

    if subtitle:
        st.markdown(f'<div class="metric-pack-scope">{subtitle}</div>', unsafe_allow_html=True)

    if row1_header:
        st.markdown(f'<div class="mini-band">{row1_header}</div>', unsafe_allow_html=True)

    row1 = st.columns(3)
    with row1[0]:
        render_metric_card(
            "Contacto (avg sec)",
            pack["Contacto (avg sec)"],
            accent,
            "Tiempo Promedio de Segundos<br>Activos<br>Contacto"
        )
    with row1[1]:
        render_metric_card(
            "Improcedente (avg sec)",
            pack["Improcedente (avg sec)"],
            accent,
            "Tiempo Promedio de Segundos<br>Activos<br>Improcedente"
        )
    with row1[2]:
        render_metric_card(
            "No contactado (avg sec)",
            pack["No contactado (avg sec)"],
            accent,
            "Tiempo Promedio de Segundos<br>Activos<br>No contactado"
        )

    if row2_header:
        st.markdown(f'<div class="mini-band">{row2_header}</div>', unsafe_allow_html=True)

    row2 = st.columns(3)
    with row2[0]:
        render_metric_card(
            "% Colgó Agente",
            pack["% Colgó Agente"],
            accent,
            "Colgó Agente<br>En porcentaje"
        )
    with row2[1]:
        render_metric_card(
            "Bloqueo de Discard",
            pack["Bloqueo de Discard"],
            accent,
            "Bloqueo de Discard<br>No. de llamadas"
        )
    with row2[2]:
        render_metric_card(
            "AWC",
            pack["AWC"],
            accent,
            "AWC<br>Segundos"
        )


# -------------------------------
# SUMMARY / EXPORT HELPERS
# -------------------------------
def build_summary(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[group_col, "Registros", "Porcentaje"])

    out = (
        df.groupby(group_col, dropna=False)
        .size()
        .reset_index(name="Registros")
        .sort_values("Registros", ascending=False)
    )

    total = out["Registros"].sum()
    out["Porcentaje"] = np.where(total > 0, out["Registros"] / total, 0.0)
    return out


def build_team_agent_summary(df: pd.DataFrame, tip_col: str, team_col: str, agent_col: str):
    work_local = df.copy()

    if team_col not in work_local.columns:
        work_local[team_col] = "Sin supervisor"
    if agent_col not in work_local.columns:
        work_local[agent_col] = "Sin agente"

    work_local[team_col] = work_local[team_col].replace("", np.nan).fillna("Sin supervisor")
    work_local[agent_col] = work_local[agent_col].replace("", np.nan).fillna("Sin agente")

    team = (
        work_local.groupby([team_col, tip_col], dropna=False)
        .size()
        .reset_index(name="Registros")
    )

    agent = (
        work_local.groupby([agent_col, tip_col], dropna=False)
        .size()
        .reset_index(name="Registros")
    )

    return team, agent


def build_pbix_agent_table(df: pd.DataFrame, team_col: str, agent_col: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[
            team_col, agent_col,
            "Duración Promedio Contacto", "Total Contacto",
            "Duración Promedio Improcedente", "Total Improcedente",
            "Duración Promedio No Contactado", "Total No Contactado",
            "AWC"
        ])

    work_local = df.copy()
    work_local["Duracion_CC"] = pd.to_numeric(work_local["Duracion_CC"], errors="coerce")
    work_local["acw"] = pd.to_numeric(work_local["acw"], errors="coerce")
    work_local["Estatus_CC"] = work_local["Estatus_CC"].fillna("").astype(str).str.strip().str.upper()

    rows = []
    for (sup, agente), g in work_local.groupby([team_col, agent_col], dropna=False):
        g_cto = g[g["Estatus_CC"] == "CONTACTO"]
        g_imp = g[g["Estatus_CC"] == "IMPROCEDENTE"]
        g_nct = g[g["Estatus_CC"] == "NO CONTACTADO"]

        cto_secs = g_cto["Duracion_CC"].dropna()
        imp_secs = g_imp["Duracion_CC"].dropna()
        nct_secs = g_nct["Duracion_CC"].dropna()
        awc_vals = g["acw"].dropna()

        cto_secs = cto_secs[cto_secs > 0]
        imp_secs = imp_secs[imp_secs > 0]
        nct_secs = nct_secs[nct_secs > 0]

        rows.append({
            team_col: sup,
            agent_col: agente,
            "Duración Promedio Contacto": float(cto_secs.mean()) if not cto_secs.empty else 0.0,
            "Total Contacto": int(len(g_cto)),
            "Duración Promedio Improcedente": float(imp_secs.mean()) if not imp_secs.empty else 0.0,
            "Total Improcedente": int(len(g_imp)),
            "Duración Promedio No Contactado": float(nct_secs.mean()) if not nct_secs.empty else 0.0,
            "Total No Contactado": int(len(g_nct)),
            "AWC": float(awc_vals.mean()) if not awc_vals.empty else 0.0,
        })

    return pd.DataFrame(rows).sort_values([team_col, agent_col]).reset_index(drop=True)


def make_excel(
    detail_df: pd.DataFrame,
    summary_tip: pd.DataFrame,
    summary_team: pd.DataFrame,
    summary_agent: pd.DataFrame
) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary_tip.to_excel(writer, sheet_name="Resumen_Tipificacion", index=False)
        summary_team.to_excel(writer, sheet_name="Resumen_Equipo", index=False)
        summary_agent.to_excel(writer, sheet_name="Resumen_Agente", index=False)
        detail_df.to_excel(writer, sheet_name="Detalle", index=False)
    buffer.seek(0)
    return buffer.getvalue()


# -------------------------------
# SIDEBAR
# -------------------------------
with st.sidebar:
    st.subheader("Conexión CC2 + JV")

    if not JV_API_KEY or not CC2_API_KEY:
        st.error("Faltan credenciales API en .streamlit/secrets.toml")

    if not SQL_HOST or not SQL_DATABASE or not SQL_USERNAME or not SQL_PASSWORD:
        st.error("Faltan credenciales SQL Server en .streamlit/secrets.toml")

    if st.button("Recargar datos ahora"):
        st.cache_data.clear()
        st.rerun()

    st.subheader("Período")
    view_mode = st.radio(
        "Selecciona el período",
        ["Hoy", "Día hábil anterior", "Elegir fecha"],
        index=1
    )

    selected_date = None
    if view_mode == "Elegir fecha":
        selected_date = st.date_input("Fecha", value=mexico_now().date())

    st.subheader("Vista de tipificación")
    tip_view = st.radio(
        "Nivel de detalle",
        ["Resumen general", "Detalle completo"],
        index=1
    )


# -------------------------------
# VALIDATION
# -------------------------------
if not JV_API_KEY or not CC2_API_KEY:
    st.title("Tipificaciones de Contacto - JV y CC2")
    st.warning("Agrega tus credenciales API en `.streamlit/secrets.toml`.")
    st.stop()

if not SQL_HOST or not SQL_DATABASE or not SQL_USERNAME or not SQL_PASSWORD:
    st.title("Tipificaciones de Contacto - JV y CC2")
    st.warning("Agrega tus credenciales de SQL Server en `.streamlit/secrets.toml`.")
    st.stop()


# -------------------------------
# TITLE
# -------------------------------
st.title("Tipificaciones de Contacto - JV y CC2")
st.caption("Resumen general y desglose por centro de operación.")


# -------------------------------
# LOAD DATA
# -------------------------------
if view_mode == "Hoy":
    df, source_date = get_consolidado_hoy()
    visual_label = f"Hoy ({mexico_now().strftime('%Y-%m-%d %H:%M:%S')})"
    source_label = f"Datos reales de: {source_date}"
elif view_mode == "Día hábil anterior":
    df, source_date = get_consolidado_ayer()
    visual_label = f"Día hábil anterior ({source_date})"
    source_label = f"Datos reales de: {source_date}"
else:
    df = get_consolidado_exact_day(selected_date)
    source_date = selected_date
    visual_label = f"Fecha elegida ({selected_date})"
    source_label = f"Datos reales de: {source_date}"

if df.empty:
    st.error("No se encontraron registros para la vista seleccionada.")
    st.stop()


# -------------------------------
# FILTERS
# -------------------------------
work = df.copy()
work = add_supervisor_display(work)

team_col = "Supervisor_Display"
agent_col = "Gestor_CC"

work[team_col] = work[team_col].replace("", np.nan).fillna("Sin supervisor").astype(str)
work[agent_col] = work[agent_col].replace("", np.nan).fillna("Sin agente").astype(str)

tip_col = "Tipificacion_3" if tip_view == "Resumen general" else "Tipificacion_Detalle"

with st.sidebar:
    st.markdown("---")
    st.subheader("Filtros")

    center_view = st.radio(
        "Vista por centro",
        ["Ambos", "CC2", "JV"],
        index=0,
        horizontal=True
    )

    if center_view == "Ambos":
        work_centro = work.copy()
    elif center_view == "CC2":
        work_centro = work[work["Centro"].astype(str).str.upper() == "CC2"].copy()
    else:
        work_centro = work[work["Centro"].astype(str).str.upper() == "JV"].copy()

    supervisor_options = sorted(work_centro[team_col].dropna().astype(str).unique().tolist())
    selected_teams = st.multiselect("Supervisor", supervisor_options, default=supervisor_options)

    work_team = work_centro[work_centro[team_col].isin(selected_teams)].copy() if selected_teams else work_centro.iloc[0:0].copy()

    agent_options = sorted(work_team[agent_col].dropna().astype(str).unique().tolist())
    selected_agents = st.multiselect("Agente", agent_options, default=agent_options)

    work_agent = work_team[work_team[agent_col].isin(selected_agents)].copy() if selected_agents else work_team.iloc[0:0].copy()

    tip_options = sorted(work_agent[tip_col].dropna().astype(str).unique().tolist())
    selected_tip = st.multiselect("Tipificación", tip_options, default=tip_options)

if center_view == "Ambos":
    work = work.copy()
elif center_view == "CC2":
    work = work[work["Centro"].astype(str).str.upper() == "CC2"].copy()
else:
    work = work[work["Centro"].astype(str).str.upper() == "JV"].copy()

if selected_teams:
    work = work[work[team_col].isin(selected_teams)].copy()
else:
    work = work.iloc[0:0].copy()

if selected_agents:
    work = work[work[agent_col].isin(selected_agents)].copy()
else:
    work = work.iloc[0:0].copy()

if selected_tip:
    work = work[work[tip_col].isin(selected_tip)].copy()
else:
    work = work.iloc[0:0].copy()

if work.empty:
    st.warning("No hay registros con los filtros seleccionados.")
    st.stop()

TEAM_LABEL = "Supervisor"
AGENT_LABEL = "Agente"
chart_work = work.copy()


# -------------------------------
# KPIS
# -------------------------------
page1_base = df.copy()
page1_jv = page1_base[page1_base["Centro"].astype(str).str.upper() == "JV"].copy()
page1_cc2 = page1_base[page1_base["Centro"].astype(str).str.upper() == "CC2"].copy()

page1_global_pack = compute_metric_pack(page1_base)
page1_jv_pack = compute_metric_pack(page1_jv)
page1_cc2_pack = compute_metric_pack(page1_cc2)

page2_base = apply_powerbi_center_page_scope(df.copy())
page2_jv = page2_base[page2_base["Centro"].astype(str).str.upper() == "JV"].copy()
page2_cc2 = page2_base[page2_base["Centro"].astype(str).str.upper() == "CC2"].copy()

page2_jv_pack = compute_metric_pack(page2_jv)
page2_cc2_pack = compute_metric_pack(page2_cc2)

st.caption(f"Vista: {visual_label} | Centro consultado: {center_view} | {source_label}")
st.caption(f"Al corte del {mexico_now().strftime('%m/%d/%Y %I:%M:%S %p')}")

if center_view == "Ambos":
    hb1, hb2 = st.columns([1, 2])
    with hb1:
        render_pbix_band("MÉTRICAS GLOBALES")
    with hb2:
        render_pbix_band("MÉTRICAS POR CENTRO DE OPERACIÓN")
else:
    render_pbix_band("MÉTRICAS POR CENTRO DE OPERACIÓN")

render_pbix_legend()

if center_view == "Ambos":
    g1, g2, g3 = st.columns(3)

    with g1:
        render_metric_pack(
            "Consolidado general",
            page1_global_pack,
            accent="#9b87f5"
        )

    with g2:
        render_metric_pack(
            "CC JV",
            page1_jv_pack,
            accent="#00c2a8"
        )

    with g3:
        render_metric_pack(
            "CC2",
            page1_cc2_pack,
            accent="#ff6b6b"
        )

elif center_view == "JV":
    render_metric_pack(
        "CC JV",
        page1_jv_pack,
        accent="#00c2a8"
    )

elif center_view == "CC2":
    render_metric_pack(
        "CC2",
        page1_cc2_pack,
        accent="#ff6b6b"
    )


# -------------------------------
# PAGE-SPECIFIC CENTER BLOCKS
# -------------------------------
if center_view == "Ambos":
    c1, c2 = st.columns(2)

    with c1:
        render_center_page_title("CCenter JV")
        render_metric_pack(
            "Indicadores del centro",
            page2_jv_pack,
            accent="#00c2a8",
            row1_header="Tiempo Promedio de Segundos Activos",
            row2_header="% Colgó Agente / Bloqueo de Discard / AWC"
        )

    with c2:
        render_center_page_title("CC2")
        render_metric_pack(
            "Indicadores del centro",
            page2_cc2_pack,
            accent="#ff6b6b",
            row1_header="Tiempo Promedio de Segundos Activos",
            row2_header="% Colgó Agente / Bloqueo de Discard / AWC"
        )

elif center_view == "JV":
    render_center_page_title("CCenter JV")
    render_metric_pack(
        "Indicadores del centro",
        page2_jv_pack,
        accent="#00c2a8",
        row1_header="Tiempo Promedio de Segundos Activos",
        row2_header="% Colgó Agente / Bloqueo de Discard / AWC"
    )

elif center_view == "CC2":
    render_center_page_title("CC2")
    render_metric_pack(
        "Indicadores del centro",
        page2_cc2_pack,
        accent="#ff6b6b",
        row1_header="Tiempo Promedio de Segundos Activos",
        row2_header="% Colgó Agente / Bloqueo de Discard / AWC"
    )


# -------------------------------
# SUMMARIES
# -------------------------------
summary_tip = build_summary(chart_work, tip_col)

if tip_col == "Tipificacion_3":
    order_map = {k: i for i, k in enumerate(TIP_ORDER_3)}
    summary_tip["OrdenTmp"] = summary_tip[tip_col].map(order_map).fillna(999)
    summary_tip = summary_tip.sort_values(["OrdenTmp", "Registros"], ascending=[True, False]).drop(columns="OrdenTmp")

team_summary_long, agent_summary_long = build_team_agent_summary(chart_work, tip_col, team_col, agent_col)

team_pivot = (
    team_summary_long.pivot(index=team_col, columns=tip_col, values="Registros")
    .fillna(0)
    .reset_index()
)

agent_pivot = build_pbix_agent_table(work, team_col, agent_col)


# -------------------------------
# CHARTS
# -------------------------------
st.markdown('<div class="section-title">Desglose por tipificación</div>', unsafe_allow_html=True)
st.markdown('<div class="section-subtitle">Distribución de registros en la vista consultada.</div>', unsafe_allow_html=True)

left, right = st.columns([0.95, 1.05])

with left:
    fig_tip = px.bar(
        summary_tip,
        x=tip_col,
        y="Registros",
        text="Registros",
        title="Registros por tipificación",
    )
    fig_tip.update_traces(textposition="outside")
    fig_tip.update_layout(
        xaxis_title="Tipificación",
        yaxis_title="Registros",
        uniformtext_minsize=8,
        uniformtext_mode="hide",
    )
    st.plotly_chart(fig_tip, use_container_width=True)

with right:
    fig_donut = px.pie(
        summary_tip,
        names=tip_col,
        values="Registros",
        hole=0.55,
        title="Participación porcentual por tipificación",
    )
    fig_donut.update_traces(textinfo="percent+label")
    st.plotly_chart(fig_donut, use_container_width=True)

st.markdown('<div class="section-title">Desglose por supervisor</div>', unsafe_allow_html=True)
st.markdown('<div class="section-subtitle">Volumen de registros por supervisor y tipificación.</div>', unsafe_allow_html=True)

team_chart_df = team_summary_long.sort_values(
    [team_col, "Registros"],
    ascending=[True, False]
).copy()

team_chart_df["Label"] = team_chart_df["Registros"].astype(int).astype(str)

fig_team = px.bar(
    team_chart_df,
    x=team_col,
    y="Registros",
    color=tip_col,
    text="Label",
    title="Volumen de registros por supervisor",
    barmode="stack",
)

fig_team.update_traces(
    textposition="inside",
    textfont_size=11,
    insidetextanchor="middle",
    cliponaxis=False
)

fig_team.update_layout(
    xaxis_title=TEAM_LABEL,
    yaxis_title="Registros",
    uniformtext_minsize=8,
    uniformtext_mode="hide"
)

st.plotly_chart(fig_team, use_container_width=True)

st.markdown('<div class="section-title">Desglose por agente</div>', unsafe_allow_html=True)
st.markdown('<div class="section-subtitle">Volumen de registros por agente y tipificación.</div>', unsafe_allow_html=True)

agent_chart_df = agent_summary_long.sort_values(
    [agent_col, "Registros"],
    ascending=[True, False]
).copy()

agent_chart_df["Label"] = np.where(
    agent_chart_df["Registros"] >= 15,
    agent_chart_df["Registros"].astype(int).astype(str),
    ""
)

fig_agent = px.bar(
    agent_chart_df,
    x=agent_col,
    y="Registros",
    color=tip_col,
    text="Label",
    title="Volumen de registros por agente",
    barmode="stack",
)

fig_agent.update_traces(
    textposition="inside",
    textfont_size=10,
    insidetextanchor="middle",
    cliponaxis=False
)

fig_agent.update_layout(
    xaxis_title=AGENT_LABEL,
    yaxis_title="Registros",
    uniformtext_minsize=8,
    uniformtext_mode="hide"
)

st.plotly_chart(fig_agent, use_container_width=True)


# -------------------------------
# TABLES
# -------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "Resumen por tipificación",
    "Concentrado por supervisor",
    "Concentrado por agente",
    "Detalle de llamadas"
])

with tab1:
    show = summary_tip.copy()
    show["Porcentaje"] = (show["Porcentaje"] * 100).round(2)
    show = show.rename(columns={tip_col: "Tipificación"})
    st.dataframe(show, use_container_width=True, hide_index=True)

with tab2:
    team_show = team_pivot.copy().rename(columns={team_col: TEAM_LABEL})
    st.dataframe(team_show, use_container_width=True, hide_index=True)

with tab3:
    agent_show = agent_pivot.copy().rename(columns={
        team_col: TEAM_LABEL,
        agent_col: AGENT_LABEL
    })
    st.dataframe(agent_show, use_container_width=True, hide_index=True)

with tab4:
    detail_cols = [
        "Fecha_CC", "Centro", "Sistema", team_col, agent_col, "Tipificacion_3", "Tipificacion_Detalle",
        "Tel_Marcado_CC", "Campaña_CC", "Cliente_CC", "Duracion_CC", "Duracion_Min_CC",
        "Codigo_Accion_CC", "Codigo_Resultado_CC", "Extension_CC", "Calificacion_Int_CC",
        "Descripcion_sip_CC", "Campo_Clave", "Grabacion_CC"
    ]

    detail_cols = [c for c in detail_cols if c in work.columns]
    detail_cols = list(dict.fromkeys(detail_cols))

    detail_df = work[detail_cols].sort_values("Fecha_CC", ascending=False).copy()
    detail_df = detail_df.rename(columns=build_detail_rename_map(team_col, agent_col))

    st.dataframe(detail_df, use_container_width=True, hide_index=True)


# -------------------------------
# DOWNLOAD
# -------------------------------
excel_detail = work.sort_values("Fecha_CC", ascending=False).copy()
excel_detail = excel_detail.rename(columns=build_detail_rename_map(team_col, agent_col))

excel_summary_tip = summary_tip.copy().rename(columns={tip_col: "Tipificación"})
excel_team = team_pivot.copy().rename(columns={team_col: TEAM_LABEL})
excel_agent = agent_pivot.copy().rename(columns={
    team_col: TEAM_LABEL,
    agent_col: AGENT_LABEL
})

excel_bytes = make_excel(
    detail_df=excel_detail,
    summary_tip=excel_summary_tip,
    summary_team=excel_team,
    summary_agent=excel_agent
)

st.download_button(
    "Descargar Excel",
    data=excel_bytes,
    file_name=f"cc2_jv_tipificacion_{source_date}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
