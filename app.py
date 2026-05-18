# app.py
from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import geopandas as gpd
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

baseDirectory = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__,
            template_folder=os.path.join(baseDirectory, 'layout', 'view'),
            static_folder=os.path.join(baseDirectory, 'layout')
            )
app.secret_key = 'Phemboy'

# ─────────────────────────────────────────────
# Nama file GeoJSON dataset
# ─────────────────────────────────────────────
DATASET = {
    "pemukiman": "iniPemukiman.geojson",
    "sumber_air": "iniSumberAir.geojson",
    "jalan_utama": "iniJalan.geojson",
}

# CRS UTM zona 49S — cocok untuk Jawa Tengah/Timur
UTM_CRS = "EPSG:32749"

# ─────────────────────────────────────────────────────────────────
# Threshold DIKALIBRASI berdasarkan distribusi spasial data nyata
# Kecamatan Musuk (median jarak semua parameter ≈ 7 km).
#
# CATATAN PENTING — iniPemukiman adalah POLYGON DESA, bukan titik
# rumah. Jarak dihitung ke BOUNDARY (tepi polygon desa), sehingga:
#   - Titik di DALAM desa  → boundary dekat → kecil → Tidak Sesuai
#   - Titik di LUAR desa   → boundary = jarak ke tepi desa
#
# Distribusi aktual (400 titik grid):
#   p10 ≈ 1.2 km | p25 ≈ 3.8 km | p50 ≈ 7.0 km | p75 ≈ 10.5 km
#
# 1. Jarak ke Pemukiman (boundary polygon desa) — jauh = baik
#    Sesuai        : > 5000 m   (~68% area memenuhi)
#    Kurang Sesuai : 2000–5000 m (~18% area)
#    Tidak Sesuai  : < 2000 m   (~14% area, termasuk dalam desa)
PEMUKIMAN_SESUAI        = 5000.0  # meter
PEMUKIMAN_KURANG_SESUAI = 2000.0  # meter

# 2. Ketersediaan Air (sungai) — dekat = baik
#    Sesuai        : < 3000 m   (~18% area memenuhi)
#    Kurang Sesuai : 3000–8000 m (~38% area)
#    Tidak Sesuai  : > 8000 m   (~44% area)
AIR_SESUAI        = 3000.0  # meter
AIR_KURANG_SESUAI = 8000.0  # meter

# 3. Aksesibilitas (jalan) — dekat = baik
#    Sesuai        : < 3000 m   (~18% area memenuhi)
#    Kurang Sesuai : 3000–8000 m (~38% area)
#    Tidak Sesuai  : > 8000 m   (~44% area)
JALAN_SESUAI        = 3000.0  # meter
JALAN_KURANG_SESUAI = 8000.0  # meter

# ─────────────────────────────────────────────────────────────────
# Sistem Skor
#   Sesuai        = 2 poin
#   Kurang Sesuai = 1 poin
#   Tidak Sesuai  = 0 poin
# Total maks = 6 poin
#
# Klasifikasi akhir (disesuaikan realitas wilayah):
#   Layak         : 5 – 6 poin  (unggul di ≥2 parameter + 1 menengah)
#   Cukup Layak   : 3 – 4 poin
#   Tidak Layak   : 0 – 2 poin
# ─────────────────────────────────────────────────────────────────
SKOR = {"Sesuai": 2, "Kurang Sesuai": 1, "Tidak Sesuai": 0}
SKOR_LAYAK       = 5   # >= nilai ini = Layak
SKOR_CUKUP_LAYAK = 3   # >= nilai ini = Cukup Layak


def _load_and_project(path, utm_crs, fallback_gdf=None):
    """Muat GeoJSON dan proyeksikan ke UTM; kembalikan GDF UTM."""
    gdf = gpd.read_file(path)
    try:
        return gdf.to_crs(utm_crs)
    except Exception:
        return gdf


def _titik_utm(lon, lat, utm_crs):
    """Buat GeoDataFrame titik tunggal dalam CRS UTM."""
    gdf = gpd.GeoDataFrame(
        [{"geometry": Point(lon, lat)}],
        geometry="geometry",
        crs="EPSG:4326"
    )
    try:
        return gdf.to_crs(utm_crs)
    except Exception:
        return gdf


def _klasifikasi_pemukiman(jarak_boundary_m):
    """
    Semakin JAUH dari tepi (boundary) desa → semakin baik.
    Sesuai > 5000 m | Kurang Sesuai 2000–5000 m | Tidak Sesuai < 2000 m

    Catatan: jarak dihitung ke BOUNDARY polygon desa, bukan interior,
    agar titik di dalam desa tetap terdeteksi sebagai 'dekat pemukiman'.
    """
    if jarak_boundary_m > PEMUKIMAN_SESUAI:
        return "Sesuai"
    elif jarak_boundary_m >= PEMUKIMAN_KURANG_SESUAI:
        return "Kurang Sesuai"
    else:
        return "Tidak Sesuai"


def _klasifikasi_air(jarak_m):
    """
    Semakin DEKAT dengan sumber air → semakin baik.
    Sesuai < 500 m | Kurang Sesuai 500–1000 m | Tidak Sesuai > 1000 m
    """
    if jarak_m < AIR_SESUAI:
        return "Sesuai"
    elif jarak_m <= AIR_KURANG_SESUAI:
        return "Kurang Sesuai"
    else:
        return "Tidak Sesuai"


def _klasifikasi_jalan(jarak_m):
    """
    Semakin DEKAT dengan jalan → semakin baik.
    Sesuai < 3000 m | Kurang Sesuai 3000–8000 m | Tidak Sesuai > 8000 m
    """
    if jarak_m < JALAN_SESUAI:
        return "Sesuai"
    elif jarak_m <= JALAN_KURANG_SESUAI:
        return "Kurang Sesuai"
    else:
        return "Tidak Sesuai"


def analyze_feasibility(lon, lat):
    pemukiman_path = os.path.join(baseDirectory, "dataset", DATASET["pemukiman"])
    air_path       = os.path.join(baseDirectory, "dataset", DATASET["sumber_air"])
    jalan_path     = os.path.join(baseDirectory, "dataset", DATASET["jalan_utama"])

    titik_utm = _titik_utm(lon, lat, UTM_CRS)

    gdf_pemukiman = _load_and_project(pemukiman_path, UTM_CRS)
    gdf_air       = _load_and_project(air_path, UTM_CRS)
    gdf_jalan     = _load_and_project(jalan_path, UTM_CRS)

    # Cast ke BaseGeometry agar Pylance tidak ambigu pada parameter `.distance()`
    titik_geom: BaseGeometry = titik_utm.geometry.iloc[0]

    # ── PEMUKIMAN: hitung jarak ke BOUNDARY polygon desa ──────────────────
    # iniPemukiman berisi polygon desa (bukan titik rumah).
    # Titik di dalam desa → jarak ke polygon = 0 (salah: terkesan "sangat jauh").
    # Solusi: hitung ke boundary (tepi) agar titik dalam desa = jarak kecil = Tidak Sesuai.
    gdf_pem_boundary = gdf_pemukiman.copy()
    gdf_pem_boundary["geometry"] = gdf_pemukiman.geometry.boundary
    jarak_pemukiman = float(gdf_pem_boundary.geometry.distance(titik_geom).min())

    jarak_air   = float(gdf_air.geometry.distance(titik_geom).min())
    jarak_jalan = float(gdf_jalan.geometry.distance(titik_geom).min())

    # Klasifikasi per parameter
    klas_pemukiman = _klasifikasi_pemukiman(jarak_pemukiman)
    klas_air       = _klasifikasi_air(jarak_air)
    klas_jalan     = _klasifikasi_jalan(jarak_jalan)

    # Hitung total skor
    total_skor = SKOR[klas_pemukiman] + SKOR[klas_air] + SKOR[klas_jalan]

    # Klasifikasi akhir berdasarkan total skor (maks 6)
    # Layak ≥ 5 | Cukup Layak ≥ 3 | Tidak Layak < 3
    if total_skor >= SKOR_LAYAK:
        klasifikasi = "Layak"
        warna = "green"
    elif total_skor >= SKOR_CUKUP_LAYAK:
        klasifikasi = "Cukup Layak"
        warna = "orange"
    else:
        klasifikasi = "Tidak Layak"
        warna = "red"

    penjelasan = (
        f"[Pemukiman] {jarak_pemukiman:.0f} m ke tepi desa → {klas_pemukiman} \n"
        #f"(Sesuai >5000 m | Kurang Sesuai 2000–5000 m | Tidak Sesuai <2000 m). "
        f"[Sumber Air] {jarak_air:.0f} m → {klas_air} \n"
        #f"(Sesuai <3000 m | Kurang Sesuai 3000–8000 m | Tidak Sesuai >8000 m). "
        f"[Aksesibilitas] {jarak_jalan:.0f} m ke jalan → {klas_jalan} \n"
        #f"(Sesuai <3000 m | Kurang Sesuai 3000–8000 m | Tidak Sesuai >8000 m). "
        f"Skor total: {total_skor}/6."
    )

    return {
        "klasifikasi": klasifikasi,
        "warna": warna,
        "skor_total": total_skor,
        "penjelasan": penjelasan,
        # Detail per parameter
        "detail": {
            "pemukiman": {
                "jarak_m": jarak_pemukiman,
                "status": klas_pemukiman,
                "skor": SKOR[klas_pemukiman],
            },
            "sumber_air": {
                "jarak_m": jarak_air,
                "status": klas_air,
                "skor": SKOR[klas_air],
            },
            "jalan_utama": {
                "jarak_m": jarak_jalan,
                "status": klas_jalan,
                "skor": SKOR[klas_jalan],
            },
        },
    }


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload JSON diperlukan (lat, lon)"}), 400
    lat = data.get("lat")
    lon = data.get("lon")
    if lat is None or lon is None:
        return jsonify({"error": "Parameter lat dan lon dibutuhkan"}), 400
    try:
        hasil = analyze_feasibility(float(lon), float(lat))
    except Exception as e:
        return jsonify({"error": f"Kesalahan saat analisa: {str(e)}"}), 500
    return jsonify(hasil)


@app.route("/dataset/<path:filename>")
def dataset_files(filename):
    dataset_folder = os.path.join(baseDirectory, "dataset")
    return send_from_directory(dataset_folder, filename)


@app.route("/result-fragment")
def result_fragment():
    return render_template("result.html")


if __name__ == "__main__":
    app.run(debug=True)