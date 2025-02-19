from celery import shared_task
from requests import get
from yaml import Loader
from yaml import load as load_yaml
from django.core.mail import EmailMultiAlternatives

from backend.models import Category, Parameter, Product, ProductInfo, ProductParameter, Shop
from easy_thumbnails.files import get_thumbnailer
from django.core.files.base import ContentFile  # Needed to create file-like objects
import io # for working with in-memory image files

@shared_task()
def send_email(title, message,  from_email, email,):
    msg = EmailMultiAlternatives(
        subject=title,
        body=message,
        from_email=from_email,
        to=email
    )
    msg.send()

@shared_task()
def generate_product_thumbnail(product_id, image_url):
    """
    Generates a thumbnail for a product asynchronously.
    """
    try:
        response = get(image_url, stream=True)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        # Read image content into memory
        image_content = io.BytesIO(response.content)

        # Create a content file from the image
        image_file = ContentFile(image_content.read(), name=f"product_{product_id}.jpg")  # Or .png, depending on the source
        
        product = Product.objects.get(id=product_id)  # Assuming you have a Product model
        product.image.save(f"product_{product_id}.jpg", image_file, save=True) # Assumes your Product model has an ImageField named 'image'

        # Generate thumbnail options
        options = {'size': (200, 200), 'crop': True} # Example thumbnail size
        thumbnailer = get_thumbnailer(product.image)
        thumbnailer.get_thumbnail(options)

        return True
    except Exception as e:
        print(f"Thumbnail generation failed for product {product_id}: {e}")
        return False


@shared_task()
def do_import(url, user_id):
    stream = get(url).content
    try:
        data = load_yaml(stream=stream, Loader=Loader)
        shop = data['shop']
        categories = data['categories']
        goods = data['goods']

    except Exception as err:
        return False

    shop, _ = Shop.objects.get_or_create(name=shop, user_id=user_id)

    for category in categories:
        category_object, _ = Category.objects.get_or_create(id=category['id'], name=category['name'])
        category_object.shops.add(shop.id)
        category_object.save()

    ProductInfo.objects.filter(shop_id=shop.id).delete()

    for item in goods:
        product, _ = Product.objects.get_or_create(name=item['name'], category_id=item['category'])

        # **Important:**  Assuming there's an 'image_url' key in your `item` dictionary.  Adjust accordingly.
        image_url = item.get('image_url')  # Get the image URL from your data
        if image_url:
            generate_product_thumbnail.delay(product.id, image_url)  # Kick off the thumbnail generation task


        product_info = ProductInfo.objects.create(product_id=product.id,
                                                  external_id=item['id'],
                                                  model=item['model'],
                                                  price=item['price'],
                                                  price_rrc=item['price_rrc'],
                                                  quantity=item['quantity'],
                                                  shop_id=shop.id)

        for name, value in item['parameters'].items():
            parameter_object, _ = Parameter.objects.get_or_create(name=name)
            ProductParameter.objects.create(product_info_id=product_info.id,
                                            parameter_id=parameter_object.id,
                                            value=value)
    return True
