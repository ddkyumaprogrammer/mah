# -*- coding: utf-8 -*-
from django.contrib.auth.decorators import login_required
from django.http.response import HttpResponse
from questionnaire.exporter.csv.questionnaire2csv import Questionnaire2Csv
from django.views.generic import TemplateView
from django.conf import settings
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View
from questionnaire.forms import ResponseForm
from questionnaire.models import Category, Questionnaire

class ConfirmView(TemplateView):
    template_name = "questionnaire/confirm.html"
    def get_context_data(self, **kwargs):
        context = super(ConfirmView, self).get_context_data(**kwargs)
        context["uuid"] = kwargs["uuid"]
        return context


class IndexView(TemplateView):
    template_name = "questionnaire/list.html"
    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        questionnaires = Questionnaire.objects.filter(is_published=True)
        if not self.request.user.is_authenticated:
            questionnaires = questionnaires.filter(need_logged_user=False)
        context["questionnaires"] = questionnaires
        return context


class QuestionnaireCompleted(TemplateView):
    template_name = "questionnaire/completed.html"
    def get_context_data(self, **kwargs):
        context = {}
        questionnaire = get_object_or_404(Questionnaire, is_published=True, id=kwargs["id"])
        context["questionnaire"] = questionnaire
        return context


class QuestionnaireDetail(View):
    def get(self, request, *args, **kwargs):
        questionnaire = get_object_or_404(Questionnaire, is_published=True, id=kwargs["id"])
        if questionnaire.template is not None and len(questionnaire.template) > 4:
            template_name = questionnaire.template
        else:
            if questionnaire.display_by_question:
                template_name = "questionnaire/questionnaire.html"
            else:
                template_name = "questionnaire/one_page_questionnaire.html"
        if questionnaire.need_logged_user and not request.user.is_authenticated:
            return redirect("%s?next=%s" % (settings.LOGIN_URL, request.path))
        categories = Category.objects.filter(questionnaire=questionnaire).order_by("order")
        form = ResponseForm(
            questionnaire=questionnaire, user=request.user, step=kwargs.get("step", 0)
        )
        context = {"response_form": form, "questionnaire": questionnaire, "categories": categories}

        return render(request, template_name, context)

    def post(self, request, *args, **kwargs):
        questionnaire = get_object_or_404(Questionnaire, is_published=True, id=kwargs["id"])
        if questionnaire.need_logged_user and not request.user.is_authenticated:
            return redirect("%s?next=%s" % (settings.LOGIN_URL, request.path))
        categories = Category.objects.filter(questionnaire=questionnaire).order_by("order")
        form = ResponseForm(
            request.POST, questionnaire=questionnaire, user=request.user, step=kwargs.get("step", 0)
        )
        context = {"response_form": form, "questionnaire": questionnaire, "categories": categories}
        if form.is_valid():
            session_key = "questionnaire_%s" % (kwargs["id"],)
            if session_key not in request.session:
                request.session[session_key] = {}
            for key, value in list(form.cleaned_data.items()):
                request.session[session_key][key] = value
                request.session.modified = True

            next_url = form.next_step_url()
            response = None
            if questionnaire.display_by_question:
                if not form.has_next_step():
                    save_form = ResponseForm(
                        request.session[session_key], questionnaire=questionnaire, user=request.user
                    )
                    response = save_form.save()
            else:
                response = form.save()

            if next_url is not None:
                return redirect(next_url)
            else:
                del request.session[session_key]
                if response is None:
                    return redirect("/")
                else:
                    next_ = request.session.get("next", None)
                    if next_ is not None:
                        if "next" in request.session:
                            del request.session["next"]
                        return redirect(next_)
                    else:
                        return redirect(
                            "questionnaire-confirmation", uuid=response.interview_uuid
                        )
        if questionnaire.template is not None and len(questionnaire.template) > 4:
            template_name = questionnaire.template
        else:
            if questionnaire.display_by_question:
                template_name = "questionnaire/questionnaire.html"
            else:
                template_name = "questionnaire/one_page_questionnaire.html"
        return render(request, template_name, context)



def serve_unprotected_result_csv(questionnaire):
    """ Return the csv corresponding to a questionnaire. """
    questionnaire_to_csv = Questionnaire2Csv(questionnaire)
    if questionnaire_to_csv.need_update():
        questionnaire_to_csv.generate_file()
    with open(questionnaire_to_csv.file_name(), "r") as csv_file:
        response = HttpResponse(csv_file.read(), content_type="text/csv")
    content_disposition = 'attachment; filename="{}.csv"'.format(questionnaire.name)
    response["Content-Disposition"] = content_disposition
    return response

@login_required
def serve_protected_result(request, questionnaire):
    """ Return the csv only if the user is logged. """
    return serve_unprotected_result_csv(questionnaire)

def serve_result_csv(request, primary_key):
    """ ... only if the questionnaire does not require login or the user is logged.
    :param int primary_key: The primary key of the questionnaire. """
    questionnaire = get_object_or_404(Questionnaire, pk=primary_key)
    if questionnaire.need_logged_user:
        return serve_protected_result(request, questionnaire)
    return serve_unprotected_result_csv(questionnaire)
