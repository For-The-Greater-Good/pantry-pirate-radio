"""Geographic constants for geocoding validation.

This module contains geographic bounds for the United States
and individual states, used for coordinate validation.
"""

# Continental US bounds (excluding Alaska and Hawaii for most operations)
US_BOUNDS = {
    "min_lat": 24.396308,  # Southern tip of Florida
    "max_lat": 49.384358,  # Northern border with Canada
    "min_lon": -125.0,  # West coast
    "max_lon": -66.93457,  # East coast
}

# State-specific bounds for validation
STATE_BOUNDS = {
    "AL": {
        "min_lat": 30.223334,
        "max_lat": 35.008028,
        "min_lon": -88.473227,
        "max_lon": -84.888180,
    },
    "AK": {
        "min_lat": 51.214183,
        "max_lat": 71.538800,
        "min_lon": -179.148909,
        "max_lon": -129.979511,
    },
    "AZ": {
        "min_lat": 31.332177,
        "max_lat": 37.004260,
        "min_lon": -114.818269,
        "max_lon": -109.045223,
    },
    "AR": {
        "min_lat": 33.004106,
        "max_lat": 36.499600,
        "min_lon": -94.617919,
        "max_lon": -89.644395,
    },
    "CA": {
        "min_lat": 32.534156,
        "max_lat": 42.009518,
        "min_lon": -124.409591,
        "max_lon": -114.131211,
    },
    "CO": {
        "min_lat": 36.992426,
        "max_lat": 41.003444,
        "min_lon": -109.060253,
        "max_lon": -102.041524,
    },
    "CT": {
        "min_lat": 40.950943,
        "max_lat": 42.050587,
        "min_lon": -73.727775,
        "max_lon": -71.786994,
    },
    "DE": {
        "min_lat": 38.451013,
        "max_lat": 39.839007,
        "min_lon": -75.788658,
        "max_lon": -75.048939,
    },
    "DC": {
        "min_lat": 38.791645,
        "max_lat": 38.995548,
        "min_lon": -77.119759,
        "max_lon": -76.909395,
    },
    "FL": {
        "min_lat": 24.396308,
        "max_lat": 31.000968,
        "min_lon": -87.634938,
        "max_lon": -79.974307,
    },
    "GA": {
        "min_lat": 30.355757,
        "max_lat": 35.000659,
        "min_lon": -85.605165,
        "max_lon": -80.839729,
    },
    "HI": {
        "min_lat": 18.910361,
        "max_lat": 28.402123,
        "min_lon": -178.334698,
        "max_lon": -154.806773,
    },
    "ID": {
        "min_lat": 41.988057,
        "max_lat": 49.001146,
        "min_lon": -117.243027,
        "max_lon": -111.043564,
    },
    "IL": {
        "min_lat": 36.970298,
        "max_lat": 42.508481,
        "min_lon": -91.513079,
        "max_lon": -87.494756,
    },
    "IN": {
        "min_lat": 37.771742,
        "max_lat": 41.761368,
        "min_lon": -88.097892,
        "max_lon": -84.784579,
    },
    "IA": {
        "min_lat": 40.375501,
        "max_lat": 43.501196,
        "min_lon": -96.639704,
        "max_lon": -90.140061,
    },
    "KS": {
        "min_lat": 36.993016,
        "max_lat": 40.003162,
        "min_lon": -102.051744,
        "max_lon": -94.588413,
    },
    "KY": {
        "min_lat": 36.497129,
        "max_lat": 39.147458,
        "min_lon": -89.571509,
        "max_lon": -81.964971,
    },
    "LA": {
        "min_lat": 28.928609,
        "max_lat": 33.019457,
        "min_lon": -94.043147,
        "max_lon": -88.817017,
    },
    "ME": {
        "min_lat": 42.977764,
        "max_lat": 47.459686,
        "min_lon": -71.083924,
        "max_lon": -66.949895,
    },
    "MD": {
        "min_lat": 37.911717,
        "max_lat": 39.723043,
        "min_lon": -79.487651,
        "max_lon": -75.048939,
    },
    "MA": {
        "min_lat": 41.237964,
        "max_lat": 42.886589,
        "min_lon": -73.508142,
        "max_lon": -69.928393,
    },
    "MI": {
        "min_lat": 41.696118,
        "max_lat": 48.306063,
        "min_lon": -90.418136,
        "max_lon": -82.413474,
    },
    "MN": {
        "min_lat": 43.499356,
        "max_lat": 49.384358,
        "min_lon": -97.239209,
        "max_lon": -89.491739,
    },
    "MS": {
        "min_lat": 30.173943,
        "max_lat": 34.996052,
        "min_lon": -91.655009,
        "max_lon": -88.097888,
    },
    "MO": {
        "min_lat": 35.995683,
        "max_lat": 40.613640,
        "min_lon": -95.774704,
        "max_lon": -89.098843,
    },
    "MT": {
        "min_lat": 44.358221,
        "max_lat": 49.001390,
        "min_lon": -116.050003,
        "max_lon": -104.039138,
    },
    "NE": {
        "min_lat": 39.999998,
        "max_lat": 43.001708,
        "min_lon": -104.053514,
        "max_lon": -95.308290,
    },
    "NV": {
        "min_lat": 35.001857,
        "max_lat": 42.002207,
        "min_lon": -120.005746,
        "max_lon": -114.039648,
    },
    "NH": {
        "min_lat": 42.696990,
        "max_lat": 45.305476,
        "min_lon": -72.557247,
        "max_lon": -70.610621,
    },
    "NJ": {
        "min_lat": 38.928519,
        "max_lat": 41.357423,
        "min_lon": -75.559614,
        "max_lon": -73.893979,
    },
    "NM": {
        "min_lat": 31.332301,
        "max_lat": 37.000232,
        "min_lon": -109.050173,
        "max_lon": -103.001964,
    },
    "NY": {
        "min_lat": 40.496103,
        "max_lat": 45.012810,
        "min_lon": -79.762152,
        "max_lon": -71.856214,
    },
    "NC": {
        "min_lat": 33.841469,
        "max_lat": 36.588117,
        "min_lon": -84.321869,
        "max_lon": -75.460621,
    },
    "ND": {
        "min_lat": 45.935054,
        "max_lat": 49.000574,
        "min_lon": -104.048915,
        "max_lon": -96.554507,
    },
    "OH": {
        "min_lat": 38.403202,
        "max_lat": 41.977523,
        "min_lon": -84.820159,
        "max_lon": -80.518693,
    },
    "OK": {
        "min_lat": 33.615833,
        "max_lat": 37.002206,
        "min_lon": -103.002565,
        "max_lon": -94.430662,
    },
    "OR": {
        "min_lat": 41.991794,
        "max_lat": 46.292035,
        "min_lon": -124.566244,
        "max_lon": -116.463504,
    },
    "PA": {
        "min_lat": 39.719872,
        "max_lat": 42.516072,
        "min_lon": -80.519891,
        "max_lon": -74.689516,
    },
    "RI": {
        "min_lat": 41.146339,
        "max_lat": 42.018798,
        "min_lon": -71.862772,
        "max_lon": -71.120570,
    },
    "SC": {
        "min_lat": 32.034600,
        "max_lat": 35.215402,
        "min_lon": -83.339000,
        "max_lon": -78.540800,
    },
    "SD": {
        "min_lat": 42.479635,
        "max_lat": 45.945455,
        "min_lon": -104.057698,
        "max_lon": -96.436589,
    },
    "TN": {
        "min_lat": 34.982972,
        "max_lat": 36.678118,
        "min_lon": -90.310298,
        "max_lon": -81.646900,
    },
    "TX": {
        "min_lat": 25.837377,
        "max_lat": 36.500704,
        "min_lon": -106.645646,
        "max_lon": -93.508292,
    },
    "UT": {
        "min_lat": 36.997968,
        "max_lat": 42.001567,
        "min_lon": -114.052962,
        "max_lon": -109.041058,
    },
    "VT": {
        "min_lat": 42.726853,
        "max_lat": 45.016659,
        "min_lon": -73.437740,
        "max_lon": -71.464555,
    },
    "VA": {
        "min_lat": 36.540738,
        "max_lat": 39.466012,
        "min_lon": -83.675395,
        "max_lon": -75.242266,
    },
    "WA": {
        "min_lat": 45.543541,
        "max_lat": 49.002494,
        "min_lon": -124.763068,
        "max_lon": -116.915989,
    },
    "WV": {
        "min_lat": 37.201483,
        "max_lat": 40.638801,
        "min_lon": -82.644739,
        "max_lon": -77.719519,
    },
    "WI": {
        "min_lat": 42.491983,
        "max_lat": 47.080621,
        "min_lon": -92.888114,
        "max_lon": -86.805415,
    },
    "WY": {
        "min_lat": 40.994746,
        "max_lat": 45.005904,
        "min_lon": -111.056888,
        "max_lon": -104.052140,
    },
}
