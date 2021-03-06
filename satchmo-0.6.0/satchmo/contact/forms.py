from django import newforms as forms
from django.utils.translation import ugettext as _
from satchmo.configuration import config_value, config_get_group, SettingNotSet
from satchmo.contact.models import Contact, AddressBook, PhoneNumber
from satchmo.l10n.models import Country
from satchmo.shop.models import Config
import datetime

selection = ''

class ContactInfoForm(forms.Form):
    email = forms.EmailField(max_length=30)
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    phone = forms.CharField(max_length=30)
    street1 = forms.CharField(max_length=30)
    street2 = forms.CharField(max_length=30, required=False)
    city = forms.CharField(max_length=30)
    state = forms.CharField(max_length=30, required=False)
    country = forms.CharField(max_length=30, required=False)
    postal_code = forms.CharField(max_length=10)
    copy_address = forms.BooleanField(required=False)
    ship_street1 = forms.CharField(max_length=30, required=False)
    ship_street2 = forms.CharField(max_length=30, required=False)
    ship_city = forms.CharField(max_length=30, required=False)
    ship_state = forms.CharField(max_length=30, required=False)
    ship_postal_code = forms.CharField(max_length=10, required=False)

    def __init__(self, countries, areas, *args, **kwargs):
        super(ContactInfoForm, self).__init__(*args, **kwargs)
        if areas is not None and countries is None:
            self.fields['state'] = forms.ChoiceField(choices=areas, initial=selection)
            self.fields['ship_state'] = forms.ChoiceField(choices=areas, initial=selection, required=False)
        if countries is not None:
            self.fields['country'] = forms.ChoiceField(choices=countries)

        shop_config = Config.get_shop_config()
        self._local_only = shop_config.in_country_only
        country = shop_config.sales_country
        if not country:
            self._default_country = 'US'
        else:
            self._default_country = country.iso2_code

    def clean_state(self):
        if self._local_only:
            country_iso2 = self._default_country
        else:
            country_iso2 = self.data['country']
        data = self.cleaned_data['state']
        country = Country.objects.get(iso2_code=country_iso2)
        if country.adminarea_set.count() > 0:
            if not data or data == selection:
                raise forms.ValidationError(
                    self._local_only and _('This field is required.') \
                               or _('State is required for your country.'))
        return data

    def clean_ship_state(self):
        if self.cleaned_data['copy_address']:
            if 'state' in self.cleaned_data:
                self.cleaned_data['ship_state'] = self.cleaned_data['state']
            return self.cleaned_data['ship_state']

        if self._local_only:
            country_iso2 = self._default_country
        else:
            country_iso2 = self.data['country']

        data = self.cleaned_data['ship_state']
        country = Country.objects.get(iso2_code=country_iso2)
        if country.adminarea_set.count() > 0:
            if not data or data == selection:
                raise forms.ValidationError(
                    self._local_only and _('This field is required.') \
                               or _('State is required for your country.'))
        return data

    def clean_country(self):
        if self._local_only:
            return self._default_country
        return self.cleaned_data['country']

    def ship_charfield_clean(self, field_name):
        if self.cleaned_data['copy_address']:
            if field_name in self.cleaned_data:
                self.cleaned_data['ship_' + field_name] = self.cleaned_data[field_name]
            return self.cleaned_data['ship_' + field_name]
        field = forms.CharField(max_length=30)
        return field.clean(self.cleaned_data['ship_' + field_name])

    def clean_ship_street1(self):
        return self.ship_charfield_clean('street1')

    def clean_ship_street2(self):
        if self.cleaned_data['copy_address']:
            if 'street2' in self.cleaned_data:
                self.cleaned_data['ship_street2'] = self.cleaned_data['street2']
        return self.cleaned_data['ship_street2']

    def clean_ship_city(self):
        return self.ship_charfield_clean('city')

    def clean_ship_postal_code(self):
        return self.ship_charfield_clean('postal_code')

    def save(self, contact=None, update_newsletter=True):
        """Save the contact info into the database.
        Checks to see if contact exists. If not, creates a contact
        and copies in the address and phone number."""

        if not contact:
            customer = Contact()
        else:
            customer = contact

        data = self.cleaned_data

        for field in customer.__dict__.keys():
            try:
                setattr(customer, field, data[field])
            except KeyError:
                pass

        if update_newsletter and config_get_group('NEWSLETTER'):
            from satchmo.newsletter import update_subscription
            if 'newsletter' not in data:
                subscribed = False
            else:
                subscribed = data['newsletter']
            
            update_subscription(contact, subscribed)

        if not customer.role:
            customer.role = "Customer"

        customer.save()
        
        # we need to make sure we don't blindly add new addresses
        # this isn't ideal, but until we have a way to manage addresses
        # this will force just the two addresses, shipping and billing
        # TODO: add address management like Amazon.
        
        bill_address = customer.billing_address
        if not bill_address:
            bill_address = AddressBook(contact=customer)
                
        address_keys = bill_address.__dict__.keys()
        for field in address_keys:
            try:
                setattr(bill_address, field, data[field])
            except KeyError:
                pass

        bill_address.is_default_billing = True
        
        copy_address = data['copy_address']

        ship_address = customer.shipping_address
        
        if copy_address:
            # make sure we don't have any other default shipping address
            if ship_address and ship_address.id != bill_address.id:
                ship_address.delete()
            bill_address.is_default_shipping = True

        bill_address.save()
        
        if not copy_address:
            if not ship_address or ship_address.id == bill_address.id:
                ship_address = AddressBook()
            
            for field in address_keys:
                try:
                    setattr(ship_address, field, data['ship_' + field])
                except KeyError:
                    pass
            ship_address.is_default_shipping = True
            ship_address.is_default_billing = False
            ship_address.contact = customer
            ship_address.country = bill_address.country
            ship_address.save()
            
        if not customer.primary_phone:
            phone = PhoneNumber()
            phone.primary = True
        else:
            phone = customer.primary_phone
        phone.phone = data['phone']
        phone.contact = customer
        phone.save()
        
        return customer.id

class DateTextInput(forms.TextInput):
    def render(self, name, value, attrs=None):
        if isinstance(value, datetime.date):
            value = value.strftime("%m.%d.%Y")
        return super(DateTextInput, self).render(name, value, attrs)

class ExtendedContactInfoForm(ContactInfoForm):
    """Contact form which includes birthday and newsletter."""
    dob = forms.DateField(required=False)
    newsletter = forms.BooleanField(label=_('Newsletter'), widget=forms.CheckboxInput(), required=False)
