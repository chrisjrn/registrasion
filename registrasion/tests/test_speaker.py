import pytz

from django.core.exceptions import ValidationError

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.controllers.category import CategoryController
from controller_helpers import TestingCartController
from controller_helpers import TestingInvoiceController
from registrasion.controllers.product import ProductController

from symposion.conference import models as conference_models
from symposion.proposals import models as proposal_models
from symposion.speakers import models as speaker_models

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class SpeakerTestCase(RegistrationCartTestCase):

    @classmethod
    def _create_proposals(cls):
        ''' Creates two proposals:

        - User 1 will be presenter
        - User 2 will be an additional presenter

        Each proposal is of a different ProposalKind.
        '''

        conference = conference_models.Conference.objects.create(
            title="TEST CONFERENCE.",
        )
        section = conference_models.Section.objects.create(
            conference=conference,
            name="TEST_SECTION",
            slug="testsection",
        )
        proposal_section = proposal_models.ProposalSection.objects.create(
            section=section,
            closed=False,
            published=False,
        )

        kind_1 = proposal_models.ProposalKind.objects.create(
            section=section,
            name="Kind 1",
            slug="kind1",
        )
        kind_2 = proposal_models.ProposalKind.objects.create(
            section=section,
            name="Kind 2",
            slug="kind2",
        )

        speaker_1 = speaker_models.Speaker.objects.create(
            user=cls.USER_1,
            name="Speaker 1",
            annotation="",
        )
        speaker_2 = speaker_models.Speaker.objects.create(
            user=cls.USER_2,
            name="Speaker 2",
            annotation="",
        )

        proposal_1 = proposal_models.ProposalBase.objects.create(
            kind=kind_1,
            title="Proposal 1",
            abstract="Abstract",
            description="Description",
            speaker=speaker_1,
        )
        proposal_models.AdditionalSpeaker.objects.create(
            speaker=speaker_2,
            proposalbase=proposal_1,
            status=proposal_models.AdditionalSpeaker.SPEAKING_STATUS_ACCEPTED,
        )

        proposal_2 = proposal_models.ProposalBase.objects.create(
            kind=kind_2,
            title="Proposal 2",
            abstract="Abstract",
            description="Description",
            speaker=speaker_1,
        )
        proposal_models.AdditionalSpeaker.objects.create(
            speaker=speaker_2,
            proposalbase=proposal_2,
            status=proposal_models.AdditionalSpeaker.SPEAKING_STATUS_ACCEPTED,
        )

        cls.KIND_1 = kind_1
        cls.KIND_2 = kind_2
        cls.PROPOSAL_1 = proposal_1
        cls.PROPOSAL_2 = proposal_2

    def test_create_proposals(self):
        self._create_proposals()

        self.assertIsNotNone(self.KIND_1)
        self.assertIsNotNone(self.KIND_2)
        self.assertIsNotNone(self.PROPOSAL_1)
        self.assertIsNotNone(self.PROPOSAL_2)
