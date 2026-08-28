import factory
from factory.django import DjangoModelFactory, FileField

from documents.models import Document
from users.models import User

DEFAULT_PASSWORD = 'SecurePass123!'  # pragma: allowlist secret — test fixture, never used in prod


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f'user{n}@example.com')
    firstname = factory.Faker('first_name')
    lastname = factory.Faker('last_name')
    is_verified = True
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', DEFAULT_PASSWORD)
        manager = cls._get_manager(model_class)
        return manager.create_user(*args, password=password, **kwargs)


class DocumentFactory(DjangoModelFactory):
    class Meta:
        model = Document

    name = factory.Sequence(lambda n: f'document-{n}.txt')
    owner = factory.SubFactory(UserFactory)
    file = FileField(data=b'contenu de test', filename='document.txt')
    is_active = True
