import pytz

from registrasion.models import conditions
from registrasion.controllers.product import ProductController

from symposion.conference import models as conference_models
from symposion.proposals import models as proposal_models
from symposion.reviews.models import promote_proposal
from symposion.schedule import models as schedule_models
from symposion.speakers import models as speaker_models


from registrasion.tests.test_cart import RegistrationCartTestCase

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
        proposal_section = proposal_models.ProposalSection.objects.create(  # noqa
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

    @classmethod
    def _create_flag_for_primary_speaker(cls):
        ''' Adds flag -- PROD_1 is not available unless user is a primary
        presenter of a KIND_1 '''
        flag = conditions.SpeakerFlag.objects.create(
            description="User must be presenter",
            condition=conditions.FlagBase.ENABLE_IF_TRUE,
            is_presenter=True,
            is_copresenter=False,
        )
        flag.proposal_kind.add(cls.KIND_1)
        flag.products.add(cls.PROD_1)

    @classmethod
    def _create_flag_for_additional_speaker(cls):
        ''' Adds flag -- PROD_1 is not available unless user is a primary
        presenter of a KIND_2 '''
        flag = conditions.SpeakerFlag.objects.create(
            description="User must be copresenter",
            condition=conditions.FlagBase.ENABLE_IF_TRUE,
            is_presenter=False,
            is_copresenter=True,
        )
        flag.proposal_kind.add(cls.KIND_1)
        flag.products.add(cls.PROD_1)

    def test_create_proposals(self):
        self._create_proposals()

        self.assertIsNotNone(self.KIND_1)
        self.assertIsNotNone(self.KIND_2)
        self.assertIsNotNone(self.PROPOSAL_1)
        self.assertIsNotNone(self.PROPOSAL_2)

    def test_primary_speaker_enables_item(self):
        self._create_proposals()
        self._create_flag_for_primary_speaker()

        # USER_1 cannot see PROD_1 until proposal is promoted.
        available = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available)

        # promote proposal_1 so that USER_1 becomes a speaker
        promote_proposal(self.PROPOSAL_1)

        # USER_1 can see PROD_1
        available_1 = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1],
        )
        self.assertIn(self.PROD_1, available_1)
        # USER_2 can *NOT* see PROD_1 because they're a copresenter
        available_2 = ProductController.available_products(
            self.USER_2,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available_2)

    def test_additional_speaker_enables_item(self):
        self._create_proposals()
        self._create_flag_for_additional_speaker()

        # USER_2 cannot see PROD_1 until proposal is promoted.
        available = ProductController.available_products(
            self.USER_2,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available)

        # promote proposal_1 so that USER_2 becomes an additional speaker
        promote_proposal(self.PROPOSAL_1)

        # USER_2 can see PROD_1
        available_2 = ProductController.available_products(
            self.USER_2,
            products=[self.PROD_1],
        )
        self.assertIn(self.PROD_1, available_2)
        # USER_1 can *NOT* see PROD_1 because they're a presenter
        available_1 = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available_1)

    def test_speaker_on_different_proposal_kind_does_not_enable_item(self):
        self._create_proposals()
        self._create_flag_for_primary_speaker()

        # USER_1 cannot see PROD_1 until proposal is promoted.
        available = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available)

        # promote proposal_2 so that USER_1 becomes a speaker, but of
        # KIND_2, which is not covered by this condition
        promote_proposal(self.PROPOSAL_2)

        # USER_1 cannot see PROD_1
        available_1 = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available_1)

    def test_proposal_cancelled_disables_condition(self):
        self._create_proposals()
        self._create_flag_for_primary_speaker()

        # USER_1 cannot see PROD_1 until proposal is promoted.
        available = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available)

        # promote proposal_1 so that USER_1 becomes a speaker
        promote_proposal(self.PROPOSAL_1)
        presentation = schedule_models.Presentation.objects.get(
            proposal_base=self.PROPOSAL_1
        )
        presentation.cancelled = True
        presentation.save()

        # USER_1 can *NOT* see PROD_1 because proposal_1 has been cancelled
        available_after_cancelled = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available_after_cancelled)
