"""
Base model used for products.  Stores hierarchical categories
as well as individual product level information which includes
options.
"""

import datetime
from sets import Set
from decimal import Decimal
from django.conf import settings
from django.core import validators, urlresolvers
from django.db import models
from django.utils.translation import ugettext_lazy as _
from satchmo.configuration import config_value
from satchmo.shop.utils import url_join
from satchmo.tax.models import TaxClass
from satchmo.thumbnail.field import ImageWithThumbnailField
import re, sha, random

def normalize_dir(dir_name):
    if not dir_name.startswith('./'):
        dir_name = url_join('.',dir_name)
    if dir_name.endswith("/"):
        dir_name = dir_name[:-1]
    return dir_name

def upload_dir():
    return normalize_dir(config_value('PRODUCT', 'IMAGE_DIR'))

def protected_dir():
    return normalize_dir(config_value('PRODUCT','PROTECTED_DIR'))
    

class Category(models.Model):
    """
    Basic hierarchical category model for storing products
    """
    name = models.CharField(_("Name"), core=True, max_length=200)
    slug = models.SlugField(prepopulate_from=('name',),
        help_text=_("Used for URLs"))
    parent = models.ForeignKey('self', blank=True, null=True,
        related_name='child')
    meta = models.TextField(_("Meta Description"), blank=True, null=True,
        help_text=_("Meta description for this category"))
    description = models.TextField(_("Description"), blank=True,
        help_text="Optional")

    def _recurse_for_parents_slug(self, cat_obj):
        #This is used for the urls
        p_list = []
        if cat_obj.parent_id:
            p = cat_obj.parent
            p_list.append(p.slug)
            more = self._recurse_for_parents_slug(p)
            p_list.extend(more)
        if cat_obj == self and p_list:
            p_list.reverse()
        return p_list

    def get_absolute_url(self):
        p_list = self._recurse_for_parents_slug(self)
        p_list.append(self.slug)
        return u'%s/category/%s/' % (settings.SHOP_BASE, u'/'.join(p_list))

    def _recurse_for_parents_name(self, cat_obj):
        #This is used for the visual display & save validation
        p_list = []
        if cat_obj.parent_id:
            p = cat_obj.parent
            p_list.append(p.name)
            more = self._recurse_for_parents_name(p)
            p_list.extend(more)
        if cat_obj == self and p_list:
            p_list.reverse()
        return p_list

    def get_separator(self):
        return ' :: '

    def _parents_repr(self):
        p_list = self._recurse_for_parents_name(self)
        return self.get_separator().join(p_list)
    _parents_repr.short_description = _("Category parents")

    def _recurse_for_parents_name_url(self, cat_obj):
        #Get all the absolute urls and names (for use in site navigation)
        p_list = []
        url_list = []
        if cat_obj.parent_id:
            p = cat_obj.parent
            p_list.append(p.name)
            url_list.append(p.get_absolute_url())
            more, url = self._recurse_for_parents_name_url(p)
            p_list.extend(more)
            url_list.extend(url)
        if cat_obj == self and p_list:
            p_list.reverse()
            url_list.reverse()
        return p_list, url_list

    def get_url_name(self):
        #Get a list of the url to display and the actual urls
        p_list, url_list = self._recurse_for_parents_name_url(self)
        p_list.append(self.name)
        url_list.append(self.get_absolute_url())
        return zip(p_list, url_list)

    def __unicode__(self):
        p_list = self._recurse_for_parents_name(self)
        p_list.append(self.name)
        return self.get_separator().join(p_list)

    def save(self):
        p_list = self._recurse_for_parents_name(self)
        if self.name in p_list:
            raise validators.ValidationError(_("You must not save a category in itself!"))
        super(Category, self).save()

    def _flatten(self, L):
        """
        Taken from a python newsgroup post
        """
        if type(L) != type([]): return [L]
        if L == []: return L
        return self._flatten(L[0]) + self._flatten(L[1:])

    def _recurse_for_children(self, node):
        children = []
        children.append(node)
        for child in node.child.all():
            children_list = self._recurse_for_children(child)
            children.append(children_list)
        return(children)

    def get_all_children(self):
        """
        Gets a list of all of the children categories.
        """
        children_list = self._recurse_for_children(self)
        flat_list = self._flatten(children_list[1:])
        return(flat_list)

    class Admin:
        list_display = ('name', '_parents_repr')
        ordering = ['parent', 'name']

    class Meta:
        ordering = ['parent', 'name']
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")

class OptionGroup(models.Model):
    """
    A set of options that can be applied to an item.
    Examples - Size, Color, Shape, etc
    """
    name = models.CharField(_("Name of Option Group"), max_length=50, core=True,
        help_text=_("This will be the text displayed on the product page."))
    description = models.CharField(_("Detailed Description"), max_length=100,
        blank=True,
        help_text=_("Further description of this group (i.e. shirt size vs shoe size)."))
    sort_order = models.IntegerField(_("Sort Order"),
        help_text=_("The display order for this group."))

    def __unicode__(self):
        if self.description:
            return u"%s - %s" % (self.name, self.description)
        else:
            return self.name

    class Admin:
        pass

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = _("Option Group")
        verbose_name_plural = _("Option Groups")

class OptionManager(models.Manager):
    def from_unique_id(self, str):
        (og, opt) = str.split('-')
        group = OptionGroup.objects.get(id=og)
        return Option.objects.get(optionGroup=og, value=opt)

class Option(models.Model):
    """
    These are the actual items in an OptionGroup.  If the OptionGroup is Size, then an Option
    would be Small.
    """
    objects = OptionManager()
    optionGroup = models.ForeignKey(OptionGroup, edit_inline=models.TABULAR,
        num_in_admin=5)
    name = models.CharField(_("Display value"), max_length=50, core=True)
    value = models.SlugField(_("Stored value"), max_length=50,
        prepopulate_from=('name',))
    price_change = models.DecimalField(_("Price Change"), null=True, blank=True,
        max_digits=10, decimal_places=2,
        help_text=_("This is the price differential for this option."))
    displayOrder = models.IntegerField(_("Display Order"))

    class Meta:
        ordering = ('optionGroup', 'displayOrder', 'name')
        unique_together = (('optionGroup', 'value'),)
        verbose_name = _("Option Item")
        verbose_name_plural = _("Option Items")

    def _get_unique_id(self):
        return '%s-%s' % (str(self.optionGroup.id), str(self.value),)
    # optionGroup.id-value
    unique_id = property(_get_unique_id)

    def __repr__(self):
        return u"<Option: %s>" % self.name

    def __unicode__(self):
        return u'%s: %s' % (self.optionGroup.name, self.name)

class ProductManager(models.Manager):
    def active(self):
        return self.filter(active=True)

class Product(models.Model):
    """
    Root class for all Products
    """
    name = models.CharField(_("Full Name"), max_length=255)
    slug = models.SlugField(_("Slug Name"), unique=True, prepopulate_from=('name',), core=True, blank=False)
    short_description = models.TextField(_("Short description of product"), help_text=_("This should be a 1 or 2 line description for use in product listing screens"), max_length=200, default='', blank=True)
    description = models.TextField(_("Description of product"), help_text=_("This field can contain HTML and should be a few paragraphs explaining the background of the product, and anything that would help the potential customer make their purchase."), default='', blank=True)
    category = models.ManyToManyField(Category, filter_interface=True, blank=True, verbose_name=_("Category"))
    items_in_stock = models.IntegerField(_("Number in stock"), default=0)
    meta = models.TextField(_("Meta Description"), max_length=200, blank=True, null=True, help_text=_("Meta description for this product"))
    date_added = models.DateField(_("Date added"), null=True, blank=True)
    active = models.BooleanField(_("Is product active?"), default=True, help_text=_("This will determine whether or not this product will appear on the site"))
    featured = models.BooleanField(_("Featured Item"), default=False, help_text=_("Featured items will show on the front page"))
    ordering = models.IntegerField(_("Ordering"), default=0, help_text=_("Override alphabetical order in category display"))
    weight = models.DecimalField(_("Weight"), max_digits=8, decimal_places=2, null=True, blank=True)
    length = models.DecimalField(_("Length"), max_digits=6, decimal_places=2, null=True, blank=True)
    width = models.DecimalField(_("Width"), max_digits=6, decimal_places=2, null=True, blank=True)
    height = models.DecimalField(_("Height"), max_digits=6, decimal_places=2, null=True, blank=True)
    related_items = models.ManyToManyField('self', blank=True, null=True, verbose_name=_('Related Items'), related_name='related_products')
    also_purchased = models.ManyToManyField('self', blank=True, null=True, verbose_name=_('Previously Purchased'), related_name='also_products')
    taxable = models.BooleanField(_("Taxable"), default=False)
    taxClass = models.ForeignKey(TaxClass, verbose_name=_('Tax Class'), blank=True, null=True, help_text=_("If it is taxable, what kind of tax?"))

    objects = ProductManager()

    def _get_mainImage(self):
        img = False
        if self.productimage_set.count() > 0:
            img = self.productimage_set.order_by('sort')[0]
        else:
            # try to get a main image by looking at the parent if this has one
            try:
                parent = self.productvariation.parent
                img = parent.product.main_image

            except ProductVariation.DoesNotExist:
                pass

        if not img:
            #This should be a "Image Not Found" placeholder image
            try:
                img = ProductImage.objects.filter(product__isnull=True).order_by('sort')[0]
            except IndexError:
                import sys
                print >>sys.stderr, 'Warning: default product image not found - try syncdb'

        return img

    main_image = property(_get_mainImage)

    def _get_fullPrice(self):
        """
        returns price as a Decimal
        """
                
        subtype = self.get_subtype_with_attr('unit_price')
        price = None

        if subtype:
            price = subtype.unit_price
        
        else:
            price = self._get_qty_price(1)
        if not price:
            price = Decimal("0.00")
        return price

    unit_price = property(_get_fullPrice)

    def get_qty_price(self, qty):
        """
        If QTY_DISCOUNT prices are specified, then return the appropriate discount price for
        the specified qty.  Otherwise, return the unit_price
        returns price as a Decimal
        """
        subtype = self.get_subtype_with_attr('get_qty_price')
        if subtype:
            price = subtype.get_qty_price(qty)
        
        else:
            price = self._get_qty_price(qty)
            if not price:
                price = self._get_fullPrice()
        
        return price

    def _get_qty_price(self, qty):
        """
        returns price as a Decimal
        """
        qty_discounts = self.price_set.exclude(expires__isnull=False, expires__lt=datetime.date.today()).filter(quantity__lte=qty)
        if qty_discounts.count() > 0:
            # Get the price with the quantity closest to the one specified without going over
            return qty_discounts.order_by('-quantity')[0].price
        else:
            return None

    def in_stock(self):
        subtype = self.get_subtype_with_attr('in_stock')
        if subtype:
            return subtype.in_stock
            
        if self.items_in_stock > 0:
            return True
        else:
            return False;

    def __unicode__(self):
        return self.name

    def get_absolute_url(self):
        return urlresolvers.reverse('satchmo_product',
            kwargs={'product_slug': self.slug})

    class Admin:
        list_display = ('slug', 'name', 'unit_price', 'items_in_stock', 'get_subtypes',)
        list_filter = ('category',)
        fields = (
        (None, {'fields': ('category', 'name', 'slug', 'description', 'short_description', 'date_added', 'active', 'featured', 'items_in_stock','ordering')}),
        (_('Meta Data'), {'fields': ('meta',), 'classes': 'collapse'}),
        (_('Item Dimensions'), {'fields': (('length', 'width','height',),'weight'), 'classes': 'collapse'}),
        (_('Tax'), {'fields':('taxable', 'taxClass'), 'classes': 'collapse'}),
        (_('Related Products'), {'fields':('related_items','also_purchased'),'classes':'collapse'}),
        )
        search_fields = ['slug', 'name']

    class Meta:
        ordering = ('ordering', 'name',)
        verbose_name = _("Product")
        verbose_name_plural = _("Products")

    def save(self):
        if not self.id:
            self.date_added = datetime.date.today()

        super(Product, self).save()

    def get_subtypes(self):
        types = []
        for key in config_value('PRODUCT', 'PRODUCT_TYPES'):
            app, subtype = key.split("::")
            try:
                if getattr(self, subtype.lower()):
                    types += [subtype]
            except models.ObjectDoesNotExist:
                pass
        return tuple(types)
    get_subtypes.short_description = "Product SubTypes"
    
    def get_subtype_with_attr(self, attr):
        for type in self.get_subtypes():
            subtype = getattr(self, type.lower())
            if hasattr(subtype, attr):
                return subtype
        return None

    def _has_variants(self):
        subtype = self.get_subtype_with_attr('has_variants')
        if subtype:
            return subtype.has_variants
        
        return False
    has_variants = property(_has_variants)

    def _get_category(self):
        """
        Return the primary category associated with this product
        """
        subtype = self.get_subtype_with_attr('get_category')
        if subtype:
            return subtype.get_category
        
        return self.category.all()[0].name
    get_category = property(_get_category)
    
    def _get_downloadable(self):
        """
        If this Product has any subtypes associated with it that are downloadable, then
        consider it downloadable
        """
        for prod_type in self.get_subtypes():
            subtype = getattr(self, prod_type.lower())
            if hasattr(subtype, 'is_downloadable'):
                return True
        return False
    is_downloadable = property(_get_downloadable)

    def _get_shippable(self):
        """
        If this Product has any subtypes associated with it that are not
        shippable, then consider the product not shippable.
        If it is downloadable, then we don't ship it either.
        """
        if self.is_downloadable:
            return False
        subtype = self.get_subtype_with_attr('is_shippable')
        if subtype and not subtype.is_shippable:
            return False
        return True
    is_shippable = property(_get_shippable)

class CustomProduct(models.Model):
    """
    Product which must be custom-made or ordered.
    """
    product = models.OneToOneField(Product)
    downpayment = models.IntegerField(_("Percent Downpayment"), default=20)
    deferred_shipping = models.BooleanField(_('Deferred Shipping'), 
        help_text=_('Do not charge shipping at checkout for this item.'), 
        default=False)
        
    def _is_shippable(self):
        return not self.deferred_shipping
    is_shippable = property(fget=_is_shippable)
    
    def _get_fullPrice(self):
        """
        returns price as a Decimal
        """
        return self.get_qty_price(1)
        
    unit_price = property(_get_fullPrice)
        
    def get_qty_price(self, qty):
        """
        If QTY_DISCOUNT prices are specified, then return the appropriate discount price for
        the specified qty.  Otherwise, return the unit_price
        returns price as a Decimal
        """
        price = self.product._get_qty_price(qty)
        if not price:
            price = self.product._get_fullPrice()

        return price * self.downpayment / 100
        
    def get_full_price(self, qty=1):
        """
        Return the full price, ignoring the deposit.
        """
        price = self.product._get_qty_price(qty)
        if not price:
            price = self.product._get_fullPrice()
            
        return price
    
    full_price = property(fget=get_full_price)
    
    def __unicode__(self):
        return u"CustomProduct: %s" % self.product.name
    
    class Admin:
        pass

class CustomTextField(models.Model):
    """
    A text field to be filled in by a customer.
    """

    name = models.CharField(_('Custom field name'), max_length=40, core=True)
    slug = models.SlugField()
    products = models.ForeignKey(CustomProduct, verbose_name=_('Custom Fields'),
        edit_inline=models.TABULAR, num_in_admin=3, related_name='custom_text_fields')

class ConfigurableProduct(models.Model):
    """
    Product with selectable options.
    This is a sort of virtual product that is visible to the customer, but isn't actually stocked on a shelf,
    the specific "shelf" product is determined by the selected options.
    """
    product = models.OneToOneField(Product)
    option_group = models.ManyToManyField(OptionGroup, blank=True,)
    create_subs = models.BooleanField(_("Create Variations"), default=False, help_text =_("Create ProductVariations for all this product's options.  To use this, you must first add an option, save, then return to this page and select this option."))

    def _cross_list(self, sequences):
        """
        Code taken from the Python cookbook v.2 (19.9 - Looping through the cross-product of multiple iterators)
        This is used to create all the variations associated with an product
        """
        result =[[]]
        for seq in sequences:
            result = [sublist+[item] for sublist in result for item in seq]
        return result

    def get_all_options(self):
        """
        Returns all possible combinations of options for this products OptionGroups as a List of Lists.
        Ex:
        For OptionGroups Color and Size with Options (Blue, Green) and (Large, Small) you'll get
        [['Blue', 'Small'], ['Blue', 'Large'], ['Green', 'Small'], ['Green', 'Large']]
        Note: the actual values will be instances of Option instead of strings
        """
        sublist = []
        masterlist = []
        #Create a list of all the options & create all combos of the options
        for opt in self.option_group.all():
            for value in opt.option_set.all():
                sublist.append(value)
            masterlist.append(sublist)
            sublist = []
        return self._cross_list(masterlist)

    def get_valid_options(self):
        """
        Returns the same output as get_all_options(), but filters out Options that this
        ConfigurableProduct doesn't have a ProductVariation for.
        """
        opts = self.get_all_options()
        newopts = []
        for a in opts:
            if self.get_product_count(a):
                newopts.append(a)
        return newopts

    def create_products(self):
        """
        Get a list of all the optiongroups applied to this object
        Create all combinations of the options and create variations
        """
        combinedlist = self.get_all_options()
        #Create new ProductVariation for each combo.
        for options in combinedlist:
            # Check for an existing ProductVariation.
            # Simplify this when Django #4464 is fixed.
            first_option = True
            pvs = ProductVariation.objects.filter(parent=self)
            for option in options:
                query = pvs.filter(options=option)
                if first_option:
                    first_option = False
                else:
                    query = query.filter(product__id__in=products)
                products = [variation.product.id for variation in query]

            if not products:
                # There isn't an existing ProductVariation.
                variant = Product(items_in_stock=0)
                optnames = [opt.value for opt in options]
                slug = u'%s_%s' % (self.product.slug, u'_'.join(optnames))
                while Product.objects.filter(slug=slug).count():
                    slug = u'_'.join((slug, unicode(self.product.id)))
                variant.slug = slug
                variant.save()
                pv = ProductVariation(product=variant, parent=self)
                pv.save()
                for option in options:
                    pv.options.add(option)
                variant.name = u'%s (%s)' % (
                    self.product.name, u'/'.join(optnames))
                variant.save()
        return True

    def _ensure_option_set(self, options):
        """
        Takes an iterable of Options (or str(Option)) and outputs a Set of
        str(Option) suitable for comparing to a productvariation.option_values
        """
        if not isinstance(options, Set):
            optionSet = Set()
            for opt in options:
                optionSet.add(opt.unique_id)
            return optionSet
        else:
            return options

    def get_product_from_options(self, options):
        """
        Accepts an iterable of either Option object or str(Option) objects
        Returns the product that matches or None
        """
        options = self._ensure_option_set(options)
        for member in self.productvariation_set.all():
            if member.option_values == options:
                return member.product
        return None

    def get_product_count(self, options):
        options = self._ensure_option_set(options)
        count = 0
        for variant in self.productvariation_set.filter(product__active='1'):
            if variant.option_values == options:
                count+=1
        return count

    def save(self):
        """
        Right now this only works if you save the suboptions, then go back and choose to create the variations.
        """
        super(ConfigurableProduct, self).save()

        # Doesn't work with admin - the manipulator doesn't add the option_group
        # until after save() is called.
        if self.create_subs and self.option_group.count():
            self.create_products()
            self.create_subs = False
            super(ConfigurableProduct, self).save()

    def get_absolute_url(self):
        return self.product.get_absolute_url()

    class Admin:
        pass

    def __unicode__(self):
        return self.product.slug

class DownloadableProduct(models.Model):
    """
    This type of Product is a file to be downloaded
    """
    product = models.OneToOneField(Product)
    file = models.FileField(upload_to=protected_dir())
    num_allowed_downloads = models.IntegerField(help_text=_("Number of times link can be accessed."))
    expire_minutes = models.IntegerField(help_text=_("Number of minutes the link should remain active."))
    active = models.BooleanField(help_text=_("Is this download currently active?"), default=True)
    is_shippable = False
    is_downloadable = True

    def __unicode__(self):
        return self.product.slug
    
    def create_key(self):
        salt = sha.new(str(random.random())).hexdigest()[:5]
        download_key = sha.new(salt+self.product.name).hexdigest()
        return download_key
    
    def order_success(self, order, order_item):
        from satchmo.contact.models import DownloadLink
        new_link = DownloadLink(downloadable_product=self, order=order, key=self.create_key(), num_attempts=0)
        new_link.save()
        
    class Admin:
        pass
        
#class BundledProduct(models.Model):
#    """
#    This type of Product is a group of products that are sold as a set
#    NOTE: This doesn't do anything yet - it's just an example
#    """
#    product = models.OneToOneField(Product)
#    members = models.ManyToManyField(Product, related_name='parent_productgroup_set')
#
#    class Admin:
#        pass

class ProductVariation(models.Model):
    """
    This is the real Product that is ordered when a customer orders a
    ConfigurableProduct with the matching Options selected

    """
    product = models.OneToOneField(Product)
    options = models.ManyToManyField(Option, filter_interface=True, core=True)
    parent = models.ForeignKey(ConfigurableProduct, core=True)

    def _get_fullPrice(self):
        """ Get price based on parent ConfigurableProduct """
        if not self.parent.product.unit_price:
            return None
            
        # allow explicit setting of prices.
        try:
            qty_discounts = self.price_set.exclude(expires__isnull=False, expires__lt=datetime.date.today()).filter(quantity__lte=1)
            if qty_discounts.count() > 0:
                # Get the price with the quantity closest to the one specified without going over
                return qty_discounts.order_by('-quantity')[0].price            
        except AttributeError:
            # otherwise calculate from options
            price_delta = Decimal("0.00")
            for option in self.options.all():
                if option.price_change:
                    price_delta += option.price_change
            return self.parent.product.unit_price + price_delta
    unit_price = property(_get_fullPrice)

    def _get_optionName(self):
        "Returns the options in a human readable form"
        if self.options.count() == 0:
            return self.parent.verbose_name
        output = self.parent.verbose_name + " ( "
        numProcessed = 0
        # We want the options to be sorted in a consistent manner
        optionDict = dict([(sub.optionGroup.sort_order, sub) for sub in self.options.all()])
        for optionNum in sorted(optionDict.keys()):
            numProcessed += 1
            if numProcessed == self.options.count():
                output += optionDict[optionNum].name
            else:
                output += optionDict[optionNum].name + "/"
        output += " )"
        return output
    full_name = property(_get_optionName)

    def _get_optionValues(self):
        """
        Return a set of all the valid options for this variant.
        A set makes sure we don't have to worry about ordering.
        """
        output = Set()
        for option in self.options.all():
            output.add(option.unique_id)
        return(output)
    option_values = property(_get_optionValues)

    def _has_variants(self):
        return True        
    has_variants = property(_has_variants)
    
    def _get_category(self):
        """
        Return the primary category associated with this product
        """
        return self.parent.product.category.all()[0].name
    get_category = property(_get_category)

    def _check_optionParents(self):
        groupList = []
        for option in self.options.all():
            if option.optionGroup.id in groupList:
                return(True)
            else:
                groupList.append(option.optionGroup.id)
        return(False)

    def isValidOption(self, field_data, all_data):
        raise validators.ValidationError(_("Two options from the same option group can not be applied to an item."))

    def save(self):
        pvs = ProductVariation.objects.filter(parent=self.parent)
        pvs = pvs.exclude(product=self.product)
        for pv in pvs:
            if pv.option_values == self.option_values:
                return # Don't allow duplicates

        #Ensure associated Product has a reasonable display name
        if not self.product.name:
            options = []
            for option in self.options.order_by("optionGroup"):
                options += [option.name]

            self.product.name = u'%s (%s)' % (self.parent.product.name, u'/'.join(options))
            self.product.save()

        super(ProductVariation, self).save()

    def get_absolute_url(self):
        return self.product.get_absolute_url()

    class Admin:
        pass

    def __unicode__(self):
        return self.product.slug

class ProductAttribute(models.Model):
    """
    Allows arbitrary name/value pairs (as strings) to be attached to a product.
    This is a very quick and dirty way to add extra info to a product.
    If you want more structure then this, create your own subtype to add
    whatever you want to your Products.
    """
    product = models.ForeignKey(Product, edit_inline=models.TABULAR, num_in_admin=1)
    name = models.SlugField(_("Attribute Name"), max_length=100, core=True)
    value = models.CharField(_("Value"), max_length=255)

    class Meta:
        verbose_name = _("Product Attribute")
        verbose_name_plural = _("Product Attributes")
        
class Price(models.Model):
    """
    A Price!
    Separating it out lets us have different prices for the same product for different purposes.
    For example for quantity discounts.
    The current price should be the one with the earliest expires date, and the highest quantity
    that's still below the user specified (IE: ordered) quantity, that matches a given product.
    """
    product = models.ForeignKey(Product, edit_inline=models.TABULAR, num_in_admin=2)
    price = models.DecimalField(_("Price"), max_digits=10, decimal_places=2, core=True)
    quantity = models.IntegerField(_("Discount Quantity"), default=1, help_text=_("Use this price only for this quantity or higher"))
    expires = models.DateField(null=True, blank=True)
    #TODO: add fields here for locale/currency specific pricing

    def __unicode__(self):
        return unicode(self.price)

    def save(self):
        prices = Price.objects.filter(product=self.product, quantity=self.quantity)
        ## Jump through some extra hoops to check expires - if there's a better way to handle this field I can't think of it. Expires needs to be able to be set to None in cases where there is no expiration date.
        if self.expires:
            prices = prices.filter(expires=self.expires)
        else:
            prices = prices.filter(expires__isnull=True)
        if self.id:
            prices = prices.exclude(id=self.id)
        if prices.count():
            return #Duplicate Price

        super(Price, self).save()

    class Meta:
        ordering = ['expires', '-quantity']
        verbose_name = _("Price")
        verbose_name_plural = _("Prices")
        unique_together = (("product", "quantity", "expires"),)

class ProductImage(models.Model):
    """
    A picture of an item.  Can have many pictures associated with an item.
    Thumbnails are automatically created.
    """
    product = models.ForeignKey(Product, null=True, blank=True,
        edit_inline=models.TABULAR, num_in_admin=3)
    picture = ImageWithThumbnailField(verbose_name=_('Picture'), upload_to=upload_dir(),
        name_field="_filename") #Media root is automatically prepended
    caption = models.CharField(_("Optional caption"), max_length=100,
        null=True, blank=True)
    sort = models.IntegerField(_("Sort Order"), core=True)

    def _get_filename(self):
        if self.product:
            return '%s-%s' % (self.product.slug, self.id)
        else:
            return 'default'
    _filename = property(_get_filename)

    def __unicode__(self):
        if self.product:
            return u"Image of Product %s" % self.product.slug
        elif self.caption:
            return u"Image with caption \"%s\"" % self.caption
        else:
            return u"%s" % self.picture

    class Meta:
        ordering = ['sort']
        unique_together = (('product', 'sort'),)
        verbose_name = _("Product Image")
        verbose_name_plural = _("Product Images")

    class Admin:
        pass

