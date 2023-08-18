
import secrets
import string
from home.models import Home
from home.serializer import HomeReadSerializer
from resident.models import Resident

from stand.models import Stand
from django.db.models import Q
 
# initializing size of string
N = 5

def random_numbers():
    # using secrets.choice()
    # generating random strings
    res = ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                for i in range(N))
    return res

def search_auth(stand,phone_number):
    stand_number_exists = Stand.objects.filter(stand_number=stand).exists()

    if stand_number_exists:
        phone_number_exists = Resident.objects.filter(Q(phone_number1=phone_number) | Q(phone_number2=phone_number)| Q(phone_number3=phone_number)| Q(phone_number4=phone_number)).exists()
        if phone_number_exists:
            res = True
        else:
            res = False
    
    else:
        res = False
    
    return res

def search_home(stand):
    stand_number = Home.objects.get(stand__stand_number=stand)
    serializer = HomeReadSerializer(stand_number)
    return serializer.data
    