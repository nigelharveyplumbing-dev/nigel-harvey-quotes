"""Local quote templates, material matching/quantity rules and labour hints."""

import re


JOB_TEMPLATES = [
    {"name": "Replace tap", "quote_type": "small", "job": "Remove existing tap and fit new tap including testing for leaks.", "labour": 120, "materials": [
        {"name": "Flexible Tap Connector", "quantity": 2},
        {"name": "15mm Isolating Valve", "quantity": 2},
    ]},
    {"name": "Replace toilet", "quote_type": "small", "job": "Remove existing toilet and fit new close-coupled toilet including waste connection and testing.", "labour": 180, "materials": [
        {"name": "Pan Connector", "quantity": 1},
        {"name": "Service Valve", "quantity": 1},
    ]},
    {"name": "Basin waste", "quote_type": "small", "job": "Remove faulty basin waste and fit new basin waste including testing for leaks.", "labour": 90, "materials": [
        {"name": "Basin Waste", "quantity": 1},
        {"name": "Bottle Trap Chrome", "quantity": 1},
    ]},
    {"name": "Outside tap", "quote_type": "small", "job": "Supply and fit outside tap kit with isolation and testing.", "labour": 150, "materials": [
        {"name": "Outside Tap Kit", "quantity": 1},
        {"name": "15mm Copper Pipe 3m", "quantity": 1},
        {"name": "15mm Isolating Valve", "quantity": 1},
    ]},
    {"name": "Kitchen sink waste", "quote_type": "small", "job": "Remove existing sink waste and fit new waste/trap arrangement including testing.", "labour": 120, "materials": [
        {"name": "Sink Waste Kit", "quantity": 1},
        {"name": "P Trap 1.5in", "quantity": 1},
    ]},
    {"name": "Bathroom install", "quote_type": "bathroom", "job": "Bathroom plumbing installation including first fix, second fix and sanitaryware connections.", "labour": 1800, "materials": [
        {"name": "15mm Copper Pipe 3m", "quantity": 4},
        {"name": "15mm Copper Elbow", "quantity": 10},
        {"name": "15mm Isolating Valve", "quantity": 4},
        {"name": "Basin Waste", "quantity": 1},
        {"name": "Bath Waste", "quantity": 1},
    ]},
    {"name": "Bathroom refurb", "quote_type": "bathroom", "job": "Bathroom refurbishment plumbing works including sanitaryware, wastes and connections.", "labour": 2200, "materials": [
        {"name": "15mm Copper Pipe 3m", "quantity": 4},
        {"name": "15mm Copper Elbow", "quantity": 10},
        {"name": "15mm Isolating Valve", "quantity": 4},
        {"name": "Basin Waste", "quantity": 1},
    ]},
    {"name": "Heating repair", "quote_type": "heating", "job": "Heating repair works including diagnosis, replacement parts and testing.", "labour": 150, "materials": [
        {"name": "Inhibitor 1L", "quantity": 1},
    ]},
    {"name": "Radiator install", "quote_type": "heating", "job": "Supply and fit radiator including valves and testing.", "labour": 180, "materials": [
        {"name": "Radiator Valve Pair", "quantity": 1},
        {"name": "Inhibitor 1L", "quantity": 1},
    ]},
    {"name": "Full heating system", "quote_type": "heating", "job": "Full heating system installation including pipework, controls, radiators and commissioning.", "labour": 3500, "materials": [
        {"name": "22mm Copper Pipe 3m", "quantity": 6},
        {"name": "15mm Copper Pipe 3m", "quantity": 8},
        {"name": "Magnetic Filter", "quantity": 1},
        {"name": "Inhibitor 1L", "quantity": 2},
    ]},
    {"name": "Outside tap - pipework run", "quote_type": "small", "job": "Supply hot and cold plus waste pipe for outside sink. Supply cold feed for new outside tap. Redo pipework as required, test all pipework and leave ready for customer-supplied sink.", "labour": 200, "materials": [
        {"name": "Plumbright Compression Coupling Male 15mm x 1/4", "quantity": 1},
        {"name": "Plumbright Hose Union Bib Tap Dbl Check 1/2", "quantity": 1},
        {"name": "3m Copper pipe 15mm", "quantity": 4},
        {"name": "Plumbright Isolating Valve 15mm Chrome Plated", "quantity": 4},
        {"name": "Plumbright Drain Off Cock 15mm", "quantity": 2},
        {"name": "Plumbright Endfeed Elbow 90 Degree 15mm", "quantity": 10},
        {"name": "Plumbright Endfeed Equal Tee 15mm", "quantity": 6},
        {"name": "Plumbright Solvent Waste Pipe Clips 32mm", "quantity": 2},
    ]},
    {"name": "Fridge cold water feed", "quote_type": "small", "job": "Supply and connect cold water feed for fridge, including isolation valve, pipework, fittings and testing for leaks.", "labour": 120, "materials": [
        {"name": "15mm Isolating Valve", "quantity": 1},
        {"name": "15mm Copper Pipe 3m", "quantity": 1},
        {"name": "Compression Coupler 15mm", "quantity": 2},
    ]},
    {"name": "Leak repair - bathroom", "quote_type": "small", "job": "Attend bathroom leak, identify source of leak, repair faulty pipework/fitting and test on completion.", "labour": 150, "materials": [
        {"name": "15mm Copper Pipe 3m", "quantity": 1},
        {"name": "15mm Copper Elbow", "quantity": 4},
        {"name": "15mm Straight Coupler", "quantity": 2},
    ]},
    {"name": "Replace bath taps", "quote_type": "small", "job": "Remove existing bath taps and fit replacement bath taps, including testing for leaks and checking connections.", "labour": 180, "materials": [
        {"name": "Flexible Tap Connector", "quantity": 2},
        {"name": "15mm Isolating Valve", "quantity": 2},
    ]}
]


MATERIAL_ALIAS_RULES = [
    {
        "canonical": "15mm copper pipe",
        "keywords": ["15mm copper", "copper pipe 15", "copper tube 15", "3m copper pipe 15", "plumbright copper pipe 15"],
        "category": "pipework",
    },
    {
        "canonical": "22mm copper pipe",
        "keywords": ["22mm copper", "copper pipe 22", "copper tube 22", "3m copper pipe 22"],
        "category": "pipework",
    },
    {
        "canonical": "15mm isolating valve",
        "keywords": ["15mm isolating", "isolation valve 15", "isolating valve", "service valve 15", "iso valve"],
        "category": "valves",
    },
    {
        "canonical": "double check valve 15mm",
        "keywords": ["double check", "dbl check", "check valve 15", "dcv"],
        "category": "valves",
    },
    {
        "canonical": "drain off cock 15mm",
        "keywords": ["drain off", "drain cock", "doc 15", "drain valve"],
        "category": "valves",
    },
    {
        "canonical": "wall plate elbow 15mm x 1/2",
        "keywords": ["wall plate elbow", "wallplate elbow", "back plate elbow", "15mm x 1/2 wall plate", "compression wall plate elbow"],
        "category": "fittings",
    },
    {
        "canonical": "hose union bib tap",
        "keywords": ["hose union bib", "bib tap", "outside tap", "garden tap"],
        "category": "taps",
    },
    {
        "canonical": "15mm compression coupler",
        "keywords": ["compression coupler 15", "compression coupling 15", "15mm coupler", "15mm coupling"],
        "category": "fittings",
    },
    {
        "canonical": "15mm endfeed elbow",
        "keywords": [
            "endfeed elbow 15",
            "endfeed elbow 90",
            "endfeed elbow 90 degree",
            "endfeed elbow 90 degree 15mm",
            "elbow 90 15",
            "elbow 90 degree 15",
            "90 degree elbow 15",
            "90 degree elbow 15mm",
            "15mm endfeed elbow",
            "15mm elbow",
            "end feed elbow",
            "plumbright endfeed elbow 90 degree 15mm"
        ],
        "category": "fittings",
    },
    {
        "canonical": "15mm endfeed tee",
        "keywords": ["endfeed equal tee 15", "endfeed tee 15", "15mm tee", "equal tee 15"],
        "category": "fittings",
    },
    {
        "canonical": "32mm waste pipe",
        "keywords": ["32mm waste pipe", "waste pipe 32", "solvent waste pipe 32"],
        "category": "waste",
    },
    {
        "canonical": "40mm waste pipe",
        "keywords": ["40mm waste pipe", "waste pipe 40", "solvent waste pipe 40"],
        "category": "waste",
    },
    {
        "canonical": "32mm waste pipe clips",
        "keywords": ["32mm waste clips", "waste pipe clips 32", "solvent waste pipe clips 32"],
        "category": "waste",
    },
    {
        "canonical": "40mm waste pipe clips",
        "keywords": ["40mm waste clips", "waste pipe clips 40"],
        "category": "waste",
    },
    {
        "canonical": "basin waste",
        "keywords": ["basin waste", "sink basin waste", "slotted basin waste", "unslotted basin waste"],
        "category": "waste",
    },
    {
        "canonical": "bottle trap 32mm",
        "keywords": ["bottle trap", "chrome bottle trap", "32mm bottle trap"],
        "category": "waste",
    },
    {
        "canonical": "kitchen sink waste kit",
        "keywords": ["sink waste kit", "kitchen waste kit", "basket strainer waste", "sink strainer waste"],
        "category": "waste",
    },
    {
        "canonical": "p trap 40mm",
        "keywords": ["p trap 40", "40mm trap", "sink trap", "kitchen trap"],
        "category": "waste",
    },
    {
        "canonical": "pan connector",
        "keywords": ["pan connector", "toilet connector", "wc connector", "offset pan connector", "straight pan connector"],
        "category": "toilet",
    },
    {
        "canonical": "toilet fill valve",
        "keywords": ["fill valve", "inlet valve", "toilet inlet", "cistern inlet"],
        "category": "toilet",
    },
    {
        "canonical": "toilet flush valve",
        "keywords": ["flush valve", "dual flush", "toilet siphon", "syphon"],
        "category": "toilet",
    },
    {
        "canonical": "flexible tap connector",
        "keywords": ["flexi tap", "flexible tap", "flexi connector", "tap flexi", "tap tails"],
        "category": "taps",
    },
    {
        "canonical": "bath tap connectors",
        "keywords": ["bath tap connector", "bath tap connectors", "bath flexi", "bath tap tails"],
        "category": "taps",
    },
    {
        "canonical": "ptfe tape",
        "keywords": ["ptfe", "thread tape"],
        "category": "consumables",
    },
    {
        "canonical": "silicone",
        "keywords": ["silicone", "sanitary silicone", "sealant"],
        "category": "consumables",
    },
    {
        "canonical": "pipe clips 15mm",
        "keywords": ["15mm pipe clips", "pipe clip 15", "copper clips 15"],
        "category": "clips",
    },
    {
        "canonical": "trv valve",
        "keywords": ["trv", "thermostatic radiator valve", "radiator trv"],
        "category": "heating",
    },
    {
        "canonical": "lockshield valve",
        "keywords": ["lockshield", "radiator lockshield"],
        "category": "heating",
    },
    {
        "canonical": "inhibitor 1l",
        "keywords": ["inhibitor", "central heating inhibitor", "sentinel x100", "fernox inhibitor"],
        "category": "heating",
    },
{
        "canonical": "32mm bottle trap",
        "keywords": ["32mm bottle trap", "bottle trap 32", "basin bottle trap", "chrome bottle trap", "plastic bottle trap"],
        "category": "waste",
    },
    {
        "canonical": "40mm bottle trap",
        "keywords": ["40mm bottle trap", "bottle trap 40", "sink bottle trap"],
        "category": "waste",
    },
    {
        "canonical": "32mm p trap",
        "keywords": ["32mm p trap", "p trap 32", "basin p trap"],
        "category": "waste",
    },
    {
        "canonical": "40mm p trap",
        "keywords": ["40mm p trap", "p trap 40", "sink p trap", "kitchen p trap"],
        "category": "waste",
    },
    {
        "canonical": "32mm s trap",
        "keywords": ["32mm s trap", "s trap 32", "basin s trap"],
        "category": "waste",
    },
    {
        "canonical": "40mm s trap",
        "keywords": ["40mm s trap", "s trap 40", "sink s trap"],
        "category": "waste",
    },
    {
        "canonical": "32mm shallow trap",
        "keywords": ["32mm shallow trap", "shallow basin trap", "low profile basin trap"],
        "category": "waste",
    },
    {
        "canonical": "40mm shallow trap",
        "keywords": ["40mm shallow trap", "shallow sink trap", "low profile sink trap"],
        "category": "waste",
    },
    {
        "canonical": "anti-syphon trap",
        "keywords": ["anti syphon trap", "anti-syphon trap", "resealing trap", "anti vacuum trap"],
        "category": "waste",
    },
    {
        "canonical": "32mm compression waste bend",
        "keywords": ["32mm compression bend", "32mm waste bend", "waste bend 32", "32mm knuckle bend"],
        "category": "waste",
    },
    {
        "canonical": "40mm compression waste bend",
        "keywords": ["40mm compression bend", "40mm waste bend", "waste bend 40", "40mm knuckle bend"],
        "category": "waste",
    },
    {
        "canonical": "32mm compression waste coupler",
        "keywords": ["32mm compression coupler", "32mm waste coupler", "32mm waste coupling", "waste coupling 32"],
        "category": "waste",
    },
    {
        "canonical": "40mm compression waste coupler",
        "keywords": ["40mm compression coupler", "40mm waste coupler", "40mm waste coupling", "waste coupling 40"],
        "category": "waste",
    },
    {
        "canonical": "32mm solvent weld bend",
        "keywords": ["32mm solvent bend", "32mm solvent weld bend", "solvent bend 32", "32mm swept bend"],
        "category": "waste",
    },
    {
        "canonical": "40mm solvent weld bend",
        "keywords": ["40mm solvent bend", "40mm solvent weld bend", "solvent bend 40", "40mm swept bend"],
        "category": "waste",
    },
    {
        "canonical": "32mm solvent weld coupler",
        "keywords": ["32mm solvent coupler", "32mm solvent weld coupling", "solvent coupling 32"],
        "category": "waste",
    },
    {
        "canonical": "40mm solvent weld coupler",
        "keywords": ["40mm solvent coupler", "40mm solvent weld coupling", "solvent coupling 40"],
        "category": "waste",
    },
    {
        "canonical": "32mm waste tee",
        "keywords": ["32mm waste tee", "waste tee 32", "32mm swept tee"],
        "category": "waste",
    },
    {
        "canonical": "40mm waste tee",
        "keywords": ["40mm waste tee", "waste tee 40", "40mm swept tee"],
        "category": "waste",
    },
    {
        "canonical": "slotted basin waste",
        "keywords": ["slotted basin waste", "basin waste slotted", "click clack slotted", "pop up slotted"],
        "category": "waste",
    },
    {
        "canonical": "unslotted basin waste",
        "keywords": ["unslotted basin waste", "basin waste unslotted", "click clack unslotted", "pop up unslotted"],
        "category": "waste",
    },
    {
        "canonical": "click clack basin waste",
        "keywords": ["click clack basin waste", "clicker waste", "basin clicker waste"],
        "category": "waste",
    },
    {
        "canonical": "bath waste and overflow",
        "keywords": ["bath waste", "bath waste overflow", "bath waste and overflow", "pop up bath waste"],
        "category": "waste",
    },
    {
        "canonical": "bath trap 40mm",
        "keywords": ["bath trap", "40mm bath trap", "shallow bath trap", "low level bath trap"],
        "category": "waste",
    },
    {
        "canonical": "shower trap 40mm",
        "keywords": ["shower trap", "40mm shower trap", "fast flow shower trap", "low profile shower trap"],
        "category": "waste",
    },
    {
        "canonical": "90mm shower waste",
        "keywords": ["90mm shower waste", "90mm shower trap", "shower waste 90mm"],
        "category": "waste",
    },
    {
        "canonical": "kitchen basket strainer waste",
        "keywords": ["basket strainer", "basket strainer waste", "kitchen basket waste", "sink basket waste"],
        "category": "waste",
    },
    {
        "canonical": "single bowl sink waste kit",
        "keywords": ["single bowl waste kit", "single sink waste kit", "single bowl sink waste"],
        "category": "waste",
    },
    {
        "canonical": "1.5 bowl sink waste kit",
        "keywords": ["1.5 bowl waste kit", "one and half bowl waste", "1 1/2 bowl sink waste", "1.5 sink waste"],
        "category": "waste",
    },
    {
        "canonical": "double bowl sink waste kit",
        "keywords": ["double bowl waste kit", "double sink waste kit", "two bowl sink waste"],
        "category": "waste",
    },
    {
        "canonical": "appliance waste spigot",
        "keywords": ["appliance waste spigot", "washing machine spigot", "dishwasher spigot", "appliance connector"],
        "category": "waste",
    },
    {
        "canonical": "washing machine trap",
        "keywords": ["washing machine trap", "standpipe trap", "appliance trap", "washing machine waste trap"],
        "category": "waste",
    },
    {
        "canonical": "tundish",
        "keywords": ["tundish", "unvented tundish", "condensate tundish"],
        "category": "waste",
    },
    {
        "canonical": "solvent weld cement",
        "keywords": ["solvent weld cement", "solvent cement", "waste pipe cement"],
        "category": "consumables",
    },
{
        "canonical": "full bore isolating valve 15mm",
        "keywords": ["full bore isolating valve", "full bore valve 15"],
        "category": "valves"
    },
    {
        "canonical": "washing machine valve",
        "keywords": ["washing machine valve", "appliance valve"],
        "category": "valves"
    },
    {
        "canonical": "flexi hose 300mm",
        "keywords": ["300mm flexi", "300mm flexible hose"],
        "category": "taps"
    },
    {
        "canonical": "15mm copper olive",
        "keywords": ["15mm olive", "compression olive"],
        "category": "fittings"
    },
{
        "canonical": "fluidmaster bottom entry fill valve",
        "keywords": ["fluidmaster bottom entry", "bottom entry fill valve"],
        "category": "toilet"
    },
    {
        "canonical": "dual flush valve",
        "keywords": ["dual flush valve", "flush valve"],
        "category": "toilet"
    },
    {
        "canonical": "straight pan connector",
        "keywords": ["straight pan connector"],
        "category": "toilet"
    },
    {
        "canonical": "doughnut washer",
        "keywords": ["doughnut washer", "close coupling washer"],
        "category": "toilet"
    },
{
    "canonical": "thermostatic radiator valve",
    "keywords": ["trv", "radiator valve", "thermostatic radiator valve"],
    "category": "heating"
},
{
    "canonical": "lockshield valve",
    "keywords": ["lockshield", "lockshield valve"],
    "category": "heating"
},
{
    "canonical": "radiator bleed valve",
    "keywords": ["bleed valve", "bleed vent"],
    "category": "heating"
},
{
    "canonical": "radiator tail extension",
    "keywords": ["radiator tail", "tail extension"],
    "category": "heating"
},
{
    "canonical": "central heating inhibitor",
    "keywords": ["inhibitor", "fernox inhibitor"],
    "category": "heating"
},
{
    "canonical": "filling loop",
    "keywords": ["boiler filling loop", "filling loop"],
    "category": "heating"
},
{
    "canonical": "automatic air vent",
    "keywords": ["automatic air vent", "aav"],
    "category": "heating"
},
{
    "canonical": "braided filling loop",
    "keywords": ["braided filling loop", "filling loop braided", "boiler filling loop"],
    "category": "heating"
},
{
    "canonical": "angled trv",
    "keywords": ["angled trv", "angled thermostatic radiator valve", "angle trv"],
    "category": "heating"
},
{
    "canonical": "angled lockshield valve",
    "keywords": ["angled lockshield", "angle lockshield", "radiator lockshield angled"],
    "category": "heating"
},
{
    "canonical": "radiator valve tail",
    "keywords": ["radiator tail", "radiator valve tail", "rad tail"],
    "category": "heating"
},
{
    "canonical": "pressure relief valve",
    "keywords": ["prv", "pressure relief valve", "safety valve", "3 bar prv"],
    "category": "heating"
},
{
    "canonical": "expansion vessel",
    "keywords": ["expansion vessel", "ev", "vessel", "boiler vessel"],
    "category": "heating"
},
{
    "canonical": "radiator bleed valve",
    "keywords": ["bleed valve", "radiator bleed valve", "bleed vent", "air bleed"],
    "category": "heating"
},
{
    "canonical": "radiator air lock",
    "keywords": ["air lock", "cold radiator", "radiator not heating", "no heat radiator"],
    "category": "heating"
}

]


MATERIAL_CHARGING_RULES = {
    "ptfe tape": {
        "material_type": "consumable",
        "charge_method": "partial",
        "default_charge": 0.50,
        "customer_label": "Small consumable allowance",
        "note": "Partial use only. Do not charge whole roll unless specifically supplied."
    },
    "silicone": {
        "material_type": "consumable",
        "charge_method": "partial",
        "default_charge": 3.00,
        "customer_label": "Sealant allowance",
        "note": "Partial tube use unless full tube supplied."
    },
    "solvent weld cement": {
        "material_type": "consumable",
        "charge_method": "partial",
        "default_charge": 2.00,
        "customer_label": "Solvent cement allowance",
        "note": "Partial use only."
    },
    "central heating inhibitor": {
        "material_type": "chargeable",
        "charge_method": "full",
        "default_charge": None,
        "customer_label": "Central heating inhibitor",
        "note": "Normally charged as full bottle when used."
    },
    "15mm copper olive": {
        "material_type": "small_part",
        "charge_method": "small_part",
        "default_charge": 0.30,
        "customer_label": "Compression olives",
        "note": "Small fittings normally charged individually or absorbed into sundries."
    },
}


SMART_QUANTITY_RULES = [
    {"match": ["pipe clips 15mm", "15mm pipe clips"], "default_quantity": 6, "job_keywords": ["outside tap", "fridge", "pipe run"]},
    {"match": ["32mm waste pipe clips", "waste pipe clips 32"], "default_quantity": 4, "job_keywords": ["basin", "waste"]},
    {"match": ["40mm waste pipe clips", "waste pipe clips 40"], "default_quantity": 4, "job_keywords": ["sink", "shower", "waste"]},
    {"match": ["15mm copper pipe"], "default_quantity": 1, "job_keywords": ["small", "tap", "fridge", "outside tap"]},
    {"match": ["15mm endfeed elbow", "endfeed elbow"], "default_quantity": 4, "job_keywords": ["outside tap", "pipe run", "leak"]},
    {"match": ["15mm endfeed tee", "endfeed tee"], "default_quantity": 1, "job_keywords": ["outside tap", "branch"]},
    {"match": ["15mm compression coupler", "compression coupler"], "default_quantity": 2, "job_keywords": ["repair", "leak", "extension"]},
    {"match": ["15mm isolating valve", "isolating valve"], "default_quantity": 1, "job_keywords": ["fridge", "appliance"]},
    {"match": ["15mm isolating valve", "isolating valve"], "default_quantity": 2, "job_keywords": ["tap", "basin tap", "kitchen tap"]},
    {"match": ["flexi hose 300mm", "flexi hose 500mm", "flexible tap connector"], "default_quantity": 2, "job_keywords": ["tap", "basin", "kitchen"]},
    {"match": ["15mm copper olive", "olive"], "default_quantity": 2, "job_keywords": ["trv", "valve", "compression"]},
    {"match": ["radiator valve tail", "radiator tail"], "default_quantity": 2, "job_keywords": ["radiator", "trv"]},
    {"match": ["angled trv", "thermostatic radiator valve"], "default_quantity": 1, "job_keywords": ["trv", "radiator"]},
    {"match": ["angled lockshield valve", "lockshield"], "default_quantity": 1, "job_keywords": ["trv", "radiator"]},
    {"match": ["ptfe tape"], "default_quantity": 1, "job_keywords": ["any"]},
    {"match": ["silicone"], "default_quantity": 1, "job_keywords": ["bath", "basin", "toilet", "sink"]},
]


TRADE_JOB_LIBRARY = [
    {
        "name": "Outside tap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Supply and fit outside tap with isolation, double check protection, pipework, clips and testing.",
        "typical_labour": 150,
        "labour_range": "£140 - £220",
        "risk_notes": [
            "Check pipe route and wall thickness.",
            "Add drain off where pipework may freeze.",
            "Lag external pipework where exposed.",
            "Confirm double check valve/backflow protection.",
        ],
        "essential": [
            {"name": "Hose Union Bib Tap 1/2", "quantity": 1},
            {"name": "15mm Isolating Valve", "quantity": 1},
            {"name": "Double Check Valve 15mm", "quantity": 1},
            {"name": "Wall Plate Elbow 15mm x 1/2", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "Pipe Clips 15mm", "quantity": 6},
        ],
        "common": [
            {"name": "Drain Off Cock 15mm", "quantity": 1},
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Pipe Lagging 15mm", "quantity": 1},
        ],
        "optional": [
            {"name": "Outside Tap Cover", "quantity": 1},
            {"name": "Non Return Valve", "quantity": 1},
        ],
    },
    {
        "name": "Fridge cold water feed",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Supply and connect cold water feed for fridge with isolation valve, pipework, fittings and testing.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": [
            "Confirm fridge connection size before attending.",
            "Check route from nearest cold supply.",
            "Isolation valve should be accessible.",
        ],
        "essential": [
            {"name": "15mm Isolating Valve", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "Compression Coupler 15mm", "quantity": 2},
        ],
        "common": [
            {"name": "Appliance Valve", "quantity": 1},
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Pipe Clips 15mm", "quantity": 4},
        ],
        "optional": [
            {"name": "Water Filter Inline", "quantity": 1},
        ],
    },
    {
        "name": "Washing machine feed",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Install washing machine cold feed and waste connection, including isolation valve and testing.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": [
            "Check waste height and trap connection.",
            "Make sure appliance valve remains accessible.",
        ],
        "essential": [
            {"name": "Washing Machine Valve 15mm x 3/4", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "Compression Coupler 15mm", "quantity": 2},
            {"name": "Appliance Waste Trap", "quantity": 1},
        ],
        "common": [
            {"name": "Pipe Clips 15mm", "quantity": 4},
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Waste Pipe 40mm", "quantity": 1},
        ],
        "optional": [
            {"name": "Non Return Valve", "quantity": 1},
        ],
    },
    {
        "name": "Dishwasher feed",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Install dishwasher cold feed and waste connection, including isolation valve and testing.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": [
            "Check sink waste has appliance spigot.",
            "Check hose route and kinks.",
        ],
        "essential": [
            {"name": "Washing Machine Valve 15mm x 3/4", "quantity": 1},
            {"name": "Appliance Waste Trap", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
        ],
        "common": [
            {"name": "Compression Coupler 15mm", "quantity": 2},
            {"name": "Pipe Clips 15mm", "quantity": 4},
            {"name": "PTFE Tape", "quantity": 1},
        ],
        "optional": [
            {"name": "Y Piece Appliance Connector", "quantity": 1},
        ],
    },
    {
        "name": "Kitchen sink waste",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing kitchen sink waste and fit new waste/trap arrangement including testing for leaks.",
        "typical_labour": 120,
        "labour_range": "£90 - £180",
        "risk_notes": [
            "Check single or double bowl sink.",
            "Check whether appliance connections are needed.",
            "Allow for solvent weld or compression depending on existing waste.",
        ],
        "essential": [
            {"name": "Kitchen Sink Waste Kit", "quantity": 1},
            {"name": "P Trap 40mm", "quantity": 1},
            {"name": "Waste Pipe 40mm", "quantity": 1},
        ],
        "common": [
            {"name": "Waste Pipe Clips 40mm", "quantity": 4},
            {"name": "Solvent Weld Cement", "quantity": 1},
            {"name": "Silicone", "quantity": 1},
        ],
        "optional": [
            {"name": "Appliance Waste Connector", "quantity": 1},
            {"name": "Basket Strainer Waste", "quantity": 1},
        ],
    },
    {
        "name": "Basin waste",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove faulty basin waste and fit new basin waste and trap, including testing for leaks.",
        "typical_labour": 90,
        "labour_range": "£80 - £140",
        "risk_notes": [
            "Check slotted or unslotted waste.",
            "Check bottle trap condition.",
            "Old wastes can be seized.",
        ],
        "essential": [
            {"name": "Basin Waste", "quantity": 1},
            {"name": "Bottle Trap 32mm", "quantity": 1},
        ],
        "common": [
            {"name": "Waste Pipe 32mm", "quantity": 1},
            {"name": "Waste Pipe Clips 32mm", "quantity": 2},
            {"name": "Silicone", "quantity": 1},
        ],
        "optional": [
            {"name": "Chrome Bottle Trap", "quantity": 1},
        ],
    },
    {
        "name": "Replace bath taps",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing bath taps and fit replacement bath taps, including connection checks and testing for leaks.",
        "typical_labour": 180,
        "labour_range": "£150 - £260",
        "risk_notes": [
            "Access behind bath may be poor.",
            "Old tap nuts may be seized.",
            "Check if isolation valves are present.",
        ],
        "essential": [
            {"name": "Bath Tap Connectors", "quantity": 2},
            {"name": "Flexible Tap Connector", "quantity": 2},
            {"name": "PTFE Tape", "quantity": 1},
        ],
        "common": [
            {"name": "15mm Isolating Valve", "quantity": 2},
            {"name": "Tap Back Nut Spanner", "quantity": 1},
        ],
        "optional": [
            {"name": "Bath Taps", "quantity": 1},
        ],
    },
    {
        "name": "Toilet repair",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Repair toilet fault including inlet/fill valve, flush valve or siphon as required, then test operation.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": [
            "Identify whether it is fill valve, flush valve, siphon, button or overflow issue.",
            "Old cistern fittings can be brittle.",
        ],
        "essential": [
            {"name": "Toilet Fill Valve", "quantity": 1},
            {"name": "Toilet Flush Valve", "quantity": 1},
        ],
        "common": [
            {"name": "Close Coupling Kit", "quantity": 1},
            {"name": "15mm Isolating Valve", "quantity": 1},
        ],
        "optional": [
            {"name": "Toilet Button", "quantity": 1},
            {"name": "Toilet Siphon", "quantity": 1},
        ],
    },
    {
        "name": "Toilet replacement",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing toilet and fit replacement toilet including pan connector, inlet connection and testing.",
        "typical_labour": 180,
        "labour_range": "£160 - £260",
        "risk_notes": [
            "Check soil outlet direction and distance.",
            "Check floor fixing condition.",
            "Allow for new isolation valve if old one fails.",
        ],
        "essential": [
            {"name": "Pan Connector", "quantity": 1},
            {"name": "15mm Isolating Valve", "quantity": 1},
            {"name": "Flexible Tap Connector", "quantity": 1},
            {"name": "Sanitary Silicone", "quantity": 1},
        ],
        "common": [
            {"name": "Toilet Fixing Kit", "quantity": 1},
            {"name": "Close Coupling Kit", "quantity": 1},
        ],
        "optional": [
            {"name": "Offset Pan Connector", "quantity": 1},
        ],
    },
    {
        "name": "Leak repair",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Attend leak, identify source, repair faulty pipework or fitting and test on completion.",
        "typical_labour": 150,
        "labour_range": "£120 - £250",
        "risk_notes": [
            "Leak source may not be visible immediately.",
            "Access damage may be required.",
            "Allow for isolation and drain down time.",
        ],
        "essential": [
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "15mm Straight Coupler", "quantity": 2},
            {"name": "15mm Copper Elbow", "quantity": 4},
        ],
        "common": [
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Pipe Clips 15mm", "quantity": 4},
            {"name": "15mm Isolating Valve", "quantity": 1},
        ],
        "optional": [
            {"name": "22mm Copper Pipe 3m", "quantity": 1},
            {"name": "22mm Coupler", "quantity": 2},
        ],
    },
    {
        "name": "Stopcock replacement",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Replace faulty stopcock including isolation, pipework adjustment and testing.",
        "typical_labour": 180,
        "labour_range": "£150 - £280",
        "risk_notes": [
            "External stopcock may be needed to isolate supply.",
            "Old pipework may be seized or brittle.",
            "Check pipe size before attending.",
        ],
        "essential": [
            {"name": "Stopcock 15mm", "quantity": 1},
            {"name": "15mm Copper Pipe 3m", "quantity": 1},
            {"name": "Compression Coupler 15mm", "quantity": 2},
        ],
        "common": [
            {"name": "PTFE Tape", "quantity": 1},
            {"name": "Pipe Clips 15mm", "quantity": 2},
        ],
        "optional": [
            {"name": "Stopcock 22mm", "quantity": 1},
        ],
    },
    {
        "name": "Radiator valve replacement",
        "category": "Heating",
        "quote_type": "heating",
        "job": "Replace radiator valves/TRV, refill, test and bleed radiator.",
        "typical_labour": 150,
        "labour_range": "£120 - £220",
        "risk_notes": [
            "System may need partial or full drain down.",
            "Old valve tails can be seized.",
            "Check lockshield and TRV sizes.",
        ],
        "essential": [
            {"name": "TRV Valve", "quantity": 1},
            {"name": "Lockshield Valve", "quantity": 1},
            {"name": "PTFE Tape", "quantity": 1},
        ],
        "common": [
            {"name": "Inhibitor 1L", "quantity": 1},
            {"name": "15mm Copper Olive", "quantity": 2},
        ],
        "optional": [
            {"name": "Radiator Tail Extension", "quantity": 1},
        ],
    },
{
        "name": "Replace basin bottle trap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing basin trap and fit new 32mm bottle trap, including waste alignment and leak testing.",
        "typical_labour": 90,
        "labour_range": "£80 - £140",
        "risk_notes": ["Check slotted/unslotted waste.", "Old chrome traps can be seized.", "Check waste pipe alignment."],
        "essential": [
            {"name": "32mm bottle trap", "quantity": 1},
            {"name": "32mm waste pipe", "quantity": 1}
        ],
        "common": [
            {"name": "32mm compression waste coupler", "quantity": 1},
            {"name": "32mm waste pipe clips", "quantity": 2}
        ],
        "optional": [
            {"name": "slotted basin waste", "quantity": 1},
            {"name": "unslotted basin waste", "quantity": 1}
        ],
    },
    {
        "name": "Replace kitchen sink trap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove faulty kitchen sink trap/waste and fit new 40mm trap arrangement, including appliance connections where required and leak testing.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": ["Check single, 1.5 bowl or double bowl sink.", "Confirm dishwasher/washing machine spigots.", "Check existing waste is compression or solvent weld."],
        "essential": [
            {"name": "40mm p trap", "quantity": 1},
            {"name": "40mm waste pipe", "quantity": 1}
        ],
        "common": [
            {"name": "40mm compression waste bend", "quantity": 2},
            {"name": "40mm compression waste coupler", "quantity": 1},
            {"name": "appliance waste spigot", "quantity": 1}
        ],
        "optional": [
            {"name": "single bowl sink waste kit", "quantity": 1},
            {"name": "1.5 bowl sink waste kit", "quantity": 1},
            {"name": "double bowl sink waste kit", "quantity": 1}
        ],
    },
    {
        "name": "Replace bath waste",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing bath waste/overflow and fit replacement bath waste and trap, including testing for leaks.",
        "typical_labour": 150,
        "labour_range": "£120 - £220",
        "risk_notes": ["Bath access panel may be poor.", "Old bath waste can be seized.", "Check trap depth and floor void."],
        "essential": [
            {"name": "bath waste and overflow", "quantity": 1},
            {"name": "bath trap 40mm", "quantity": 1}
        ],
        "common": [
            {"name": "40mm compression waste coupler", "quantity": 1},
            {"name": "40mm waste pipe", "quantity": 1}
        ],
        "optional": [
            {"name": "40mm shallow trap", "quantity": 1}
        ],
    },
    {
        "name": "Replace shower trap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove and replace shower trap/waste where accessible, including sealing and leak testing.",
        "typical_labour": 150,
        "labour_range": "£120 - £250",
        "risk_notes": ["Access below tray is critical.", "Some trays require removal to replace trap.", "Check 90mm or low profile trap size."],
        "essential": [
            {"name": "shower trap 40mm", "quantity": 1}
        ],
        "common": [
            {"name": "90mm shower waste", "quantity": 1},
            {"name": "40mm compression waste coupler", "quantity": 1}
        ],
        "optional": [
            {"name": "40mm shallow trap", "quantity": 1}
        ],
    },
{
        "name": "Replace kitchen tap",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Remove existing kitchen tap and fit replacement tap.",
        "typical_labour": 140,
        "labour_range": "£120 - £220",
        "risk_notes": ["Check access under sink."],
        "essential": [
            {"name": "flexi hose 300mm", "quantity": 2},
            {"name": "15mm isolating valve", "quantity": 2}
        ],
        "common": [
            {"name": "15mm copper olive", "quantity": 2}
        ],
        "optional": []
    },
    {
        "name": "Install washing machine",
        "category": "Small plumbing",
        "quote_type": "small",
        "job": "Install washing machine feed and waste.",
        "typical_labour": 120,
        "labour_range": "£100 - £180",
        "risk_notes": ["Check waste spigot."],
        "essential": [
            {"name": "washing machine valve", "quantity": 1}
        ],
        "common": [
            {"name": "appliance waste spigot", "quantity": 1}
        ],
        "optional": []
    },
{
        "name": "Toilet not filling",
        "category": "Toilet repair",
        "quote_type": "small",
        "job": "Repair toilet not filling including fill valve replacement.",
        "typical_labour": 110,
        "labour_range": "£90 - £160",
        "risk_notes": ["Check side or bottom entry."],
        "essential": [
            {"name": "fluidmaster bottom entry fill valve", "quantity": 1},
            {"name": "15mm isolating valve", "quantity": 1}
        ],
        "common": [
            {"name": "15mm x 1/2 flexi hose", "quantity": 1}
        ],
        "optional": []
    },
    {
        "name": "Toilet constantly running",
        "category": "Toilet repair",
        "quote_type": "small",
        "job": "Repair toilet constantly running including flush valve replacement.",
        "typical_labour": 110,
        "labour_range": "£90 - £160",
        "risk_notes": ["Check flush valve compatibility."],
        "essential": [
            {"name": "dual flush valve", "quantity": 1},
            {"name": "doughnut washer", "quantity": 1}
        ],
        "common": [],
        "optional": []
    },
    {
        "name": "Replace toilet",
        "category": "Toilet repair",
        "quote_type": "small",
        "job": "Replace toilet including pan connector and testing.",
        "typical_labour": 220,
        "labour_range": "£180 - £320",
        "risk_notes": ["Check pan alignment."],
        "essential": [
            {"name": "straight pan connector", "quantity": 1},
            {"name": "toilet fixing kit", "quantity": 1}
        ],
        "common": [
            {"name": "doughnut washer", "quantity": 1}
        ],
        "optional": []
    },
{
    "name": "Replace TRV",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["trv", "thermostatic radiator valve", "radiator valve", "stuck valve", "valve leaking"],
    "job": "Replace faulty thermostatic radiator valve and rebalance radiator.",
    "typical_labour": 120,
    "labour_range": "£100 - £180",
    "risk_notes": ["Check valve compatibility.", "May require draining."],
    "essential": [
        {"name": "angled trv", "quantity": 1},
        {"name": "angled lockshield valve", "quantity": 1},
        {"name": "radiator valve tail", "quantity": 2}
    ],
    "common": [
        {"name": "ptfe tape", "quantity": 1},
        {"name": "15mm copper olive", "quantity": 2},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "Radiator replacement",
    "category": "Heating repair",
    "quote_type": "heating",
    "search_terms": ["replace radiator", "new radiator", "radiator install", "radiator swap", "rad replacement"],
    "job": "Remove existing radiator and install replacement radiator including valves and inhibitor.",
    "typical_labour": 240,
    "labour_range": "£180 - £350",
    "risk_notes": ["Check wall condition.", "Pipework alterations may be required."],
    "essential": [
        {"name": "angled trv", "quantity": 1},
        {"name": "angled lockshield valve", "quantity": 1},
        {"name": "radiator tail extension", "quantity": 2}
    ],
    "common": [
        {"name": "central heating inhibitor", "quantity": 1},
        {"name": "radiator bleed valve", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "Heating leak repair",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["aav", "automatic air vent", "heating leak", "radiator leak", "pressure loss", "leaking pipe", "leaking valve"],
    "job": "Investigate and repair heating leak including refill and inhibitor dosing.",
    "typical_labour": 140,
    "labour_range": "£120 - £240",
    "risk_notes": ["Leak location may increase labour.", "System may require partial drain."],
    "essential": [
        {"name": "automatic air vent", "quantity": 1},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "common": [
        {"name": "15mm compression elbow", "quantity": 2}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "System repressurisation",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["filling loop", "pressure dropping", "low pressure", "boiler pressure", "repressurise", "top up pressure"],
    "job": "Diagnose pressure loss and repressurise heating system.",
    "typical_labour": 90,
    "labour_range": "£80 - £140",
    "risk_notes": ["Pressure loss may indicate hidden leak."],
    "essential": [
        {"name": "braided filling loop", "quantity": 1}
    ],
    "common": [
        {"name": "15mm isolating valve", "quantity": 2},
        {"name": "double check valve 15mm", "quantity": 1},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "Automatic air vent replacement",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["aav", "automatic air vent", "air vent", "leaking aav", "heating air vent"],
    "job": "Replace leaking or faulty automatic air vent, refill/vent system and test.",
    "typical_labour": 130,
    "labour_range": "£110 - £200",
    "risk_notes": ["Check access to AAV.", "System may need partial drain down.", "Check pressure after repair."],
    "essential": [
        {"name": "automatic air vent", "quantity": 1},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "common": [
        {"name": "ptfe tape", "quantity": 1},
        {"name": "15mm isolating valve", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
},
{
    "name": "Pressure relief valve check",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["prv", "pressure relief valve", "prv discharge", "overflow pipe dripping", "pressure dropping"],
    "job": "Check pressure relief valve discharge and diagnose heating pressure loss.",
    "typical_labour": 130,
    "labour_range": "£110 - £220",
    "risk_notes": ["Check expansion vessel charge.", "Do not replace PRV without finding cause.", "Check discharge pipe outside."],
    "essential": [
        {"name": "pressure relief valve", "quantity": 1}
    ],
    "common": [
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "optional": [
        {"name": "expansion vessel", "quantity": 1}
    ],
    "source": "trade_knowledge"
},
{
    "name": "Cold radiator diagnosis",
    "category": "Heating repair",
    "quote_type": "small",
    "search_terms": ["cold radiator", "radiator not heating", "no heating radiator", "air lock", "bleed radiator", "stuck trv"],
    "job": "Diagnose radiator not heating, bleed/test radiator and check TRV/lockshield operation.",
    "typical_labour": 100,
    "labour_range": "£90 - £160",
    "risk_notes": ["Could be air, stuck TRV, balancing issue or sludge.", "Do not promise fix without diagnosis."],
    "essential": [
        {"name": "radiator bleed valve", "quantity": 1}
    ],
    "common": [
        {"name": "angled trv", "quantity": 1},
        {"name": "central heating inhibitor", "quantity": 1}
    ],
    "optional": [],
    "source": "trade_knowledge"
}

]


LABOUR_HINTS = {
    "small": [
        {"keywords": ["tap"], "suggestion": 120, "range": "£100 - £140"},
        {"keywords": ["toilet", "wc"], "suggestion": 180, "range": "£160 - £220"},
        {"keywords": ["waste", "trap"], "suggestion": 120, "range": "£90 - £140"},
        {"keywords": ["outside tap"], "suggestion": 150, "range": "£140 - £180"},
    ],
    "bathroom": [
        {"keywords": ["install"], "suggestion": 1800, "range": "£1,600 - £2,200"},
        {"keywords": ["refurb"], "suggestion": 2200, "range": "£2,000 - £2,800"},
        {"keywords": ["bathroom"], "suggestion": 2000, "range": "£1,600 - £2,800"},
    ],
    "heating": [
        {"keywords": ["radiator"], "suggestion": 180, "range": "£160 - £220"},
        {"keywords": ["repair"], "suggestion": 150, "range": "£120 - £220"},
        {"keywords": ["system"], "suggestion": 3500, "range": "£3,000 - £4,500"},
    ],
}


def clean_material_name_for_matching(name: str):
    cleaned = (name or "").lower()
    cleaned = re.sub(r"https?://\S+", " ", cleaned)
    cleaned = re.sub(r"[^a-z0-9/.\- ]+", " ", cleaned)
    cleaned = re.sub(r"\b(plumbright|plumbright|city plumbing|screwfix|toolstation|topps tiles|white|chrome|each|pack|pack of)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def material_alias_info(name: str, alias_rules):
    cleaned = clean_material_name_for_matching(name)
    for rule in alias_rules:
        if any(keyword in cleaned for keyword in rule["keywords"]):
            return {
                "canonical": rule["canonical"],
                "category": rule.get("category", "other"),
                "matched": True,
            }
    return {
        "canonical": cleaned or (name or "").strip().lower(),
        "category": "other",
        "matched": False,
    }


def canonical_material_name(name: str, alias_rules):
    return material_alias_info(name, alias_rules)["canonical"]


def suggest_material_quantity(name: str, job_text: str = "", *, canonical_material_name, rules):
    canonical = canonical_material_name(name)
    hay = f"{canonical} {name}".lower()
    job = (job_text or "").lower()

    best = None
    best_score = -1
    for rule in rules:
        if not any(term in hay for term in rule.get("match", [])):
            continue

        score = 1
        kws = rule.get("job_keywords", [])
        if "any" in kws:
            score += 1
        score += sum(3 for kw in kws if kw and kw != "any" and kw in job)

        if score > best_score:
            best = rule
            best_score = score

    return best.get("default_quantity", 1) if best else 1


def get_all_job_templates(job_templates, trade_job_library):
    trade_templates = []
    for job in trade_job_library:
        materials = []
        for group in ("essential", "common"):
            for item in job.get(group, []):
                copied = dict(item)
                copied["bundle_group"] = group
                materials.append(copied)

        trade_templates.append({
            "name": job["name"],
            "category": job.get("category", ""),
            "quote_type": job.get("quote_type", "small"),
            "job": job.get("job", ""),
            "labour": job.get("typical_labour", 0),
            "labour_range": job.get("labour_range", ""),
            "risk_notes": job.get("risk_notes", []),
            "materials": materials,
            "essential": job.get("essential", []),
            "common": job.get("common", []),
            "optional": job.get("optional", []),
            "source": "trade_knowledge",
        })

    existing_names = {t.get("name", "").lower() for t in job_templates}
    combined = list(job_templates)
    for template in trade_templates:
        if template["name"].lower() not in existing_names:
            combined.append(template)
    return combined
