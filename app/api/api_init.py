from app.api.routes import brands, products, keywords

all_routers = [
    brands.router,
    products.router,
    keywords.router,
]
