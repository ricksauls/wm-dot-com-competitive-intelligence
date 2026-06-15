from app.api.routes import brands, products, keywords, groups

all_routers = [
    brands.router,
    products.router,
    keywords.router,
    groups.router,
]
