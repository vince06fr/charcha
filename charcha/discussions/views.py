import json

from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.views import View 
from django.views.decorators.http import require_http_methods
from django import forms
from django.shortcuts import render, get_object_or_404
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.contenttypes.models import ContentType

from django.db.models import F
from django.forms.models import model_to_dict
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .models import UPVOTE, DOWNVOTE, FLAG
from .models import Post, Comment, Vote, User, Category
from .models import update_gchat_space

@login_required
def homepage(request):
    user = None
    if request.user.is_authenticated:
        user = request.user
    posts = Post.objects.recent_posts_with_my_votes(user)
    return render(request, "home.html", context={"posts": posts})

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ['text']
        labels = {
            'text': 'Your Comment',
        }
        help_texts = {
            'text': 'Markdown Supported',
        }

class DiscussionView(LoginRequiredMixin, View):
    def get(self, request, post_id):
        post = Post.objects.get_post_with_my_votes(post_id, 
                    request.user)
        comments = Comment.objects.best_ones_first(post_id, 
                        request.user.id)
        form = CommentForm()
        context = {"post": post, "comments": comments, "form": form}
        return render(request, "discussion.html", context=context)

    def post(self, request, post_id):
        post = Post.objects.get_post_with_my_votes(post_id, 
                    request.user)
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = post.add_comment(form.cleaned_data['text'], request.user)
            post_url = reverse('discussion', args=[post.id])
            return HttpResponseRedirect(post_url)
        else:
            context = {"post": post, "form": form, "comments": []}
            return render(request, "discussion.html", context=context)

class ReplyToComment(LoginRequiredMixin, View):
    def get(self, request, **kwargs):
        parent_comment = get_object_or_404(Comment, pk=kwargs['id'])
        post = parent_comment.post
        form = CommentForm()
        context = {"post": post, "parent_comment": parent_comment, "form": form}
        return render(request, "reply-to-comment.html", context=context)

    def post(self, request, **kwargs):
        parent_comment = get_object_or_404(Comment, pk=kwargs['id'])
        form = CommentForm(request.POST)

        if not form.is_valid():
            post = parent_comment.post
            context = {"post": post, "parent_comment": parent_comment, "form": form}
            return render(request, "reply-to-comment.html", context=context)

        comment = parent_comment.reply(form.cleaned_data['text'], request.user)
        post_url = reverse('discussion', args=[parent_comment.post.id])
        return HttpResponseRedirect(post_url)

class EditComment(LoginRequiredMixin, View):
    def get(self, request, **kwargs):
        comment = get_object_or_404(Comment, pk=kwargs['id'])
        form = CommentForm(instance=comment)
        context = {"form": form}
        return render(request, "edit-comment.html", context=context)

    def post(self, request, **kwargs):
        comment = get_object_or_404(Comment, pk=kwargs['id'])
        form = CommentForm(request.POST, instance=comment)

        if not form.is_valid():
            context = {"form": form}
            return render(request, "edit-comment.html", context=context)
        else:
            form.save()
        post_url = reverse('discussion', args=[comment.post.id])
        return HttpResponseRedirect(post_url)

class StartDiscussionForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['category', 'title', 'text']
        labels = {
            'category': 'Category',
            'title': 'Title',
            'text': 'Details'
        }
        help_text = {
            'category': 'Category',
            'title': 'Title',
            'text': 'Markdown syntax allowed'
        }

    def clean(self):
        cleaned_data = super(StartDiscussionForm, self).clean()
        url = cleaned_data.get("url")
        text = cleaned_data.get("text")
        if not (url or text):
            raise forms.ValidationError(
                "URL and Text are both empty. Please enter at least one of them."
            )
        return cleaned_data

class StartDiscussionView(LoginRequiredMixin, View):
    def get(self, request):
        form = StartDiscussionForm(initial={"author": request.user})
        form.fields['category'].queryset = Category.objects.all()
        return render(request, "submit.html", context={"form": form})

    def post(self, request):
        form = StartDiscussionForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()

            new_post_url = reverse('discussion', args=[post.id])
            return HttpResponseRedirect(new_post_url)
        else:
            return render(request, "submit.html", context={"form": form})

class EditDiscussion(LoginRequiredMixin, View):
    def get(self, request, **kwargs):
        post = get_object_or_404(Post, pk=kwargs['post_id'])
        form = StartDiscussionForm(instance=post)
        context = {"form": form}
        return render(request, "edit-discussion.html", context=context)

    def post(self, request, **kwargs):
        post = get_object_or_404(Post, pk=kwargs['post_id'])
        form = StartDiscussionForm(request.POST, instance=post)

        if not form.is_valid():
            context = {"form": form}
            return render(request, "edit-discussion.html", context=context)
        else:
            form.save()
        post_url = reverse('discussion', args=[post.id])
        return HttpResponseRedirect(post_url)


@require_http_methods(['POST'])
@csrf_exempt
def google_chatbot(request):
    event = json.loads(request.body)
    text = None
    if event['type'] == 'ADDED_TO_SPACE':
        if event['space']['type'] == 'DM':
            space_id = event['space']['name']
            email = event['user']['email']
            user_exists = update_gchat_space(email, space_id)
            if user_exists:
                text = "From now on, I will notify you of any updates in the discussions you participate."
            else:
                text = """You haven't logged in to charcha yet. Please do the following:        

                1. Remove charcha bot 
                2. Go to https://charcha.hashedin.com and login with your @hashedin.com email address
                3. Then come back and add charcha bot once again
                """
    elif event['type'] == 'REMOVED_FROM_SPACE':
        if event['space']['type'] == 'DM':
            email = event['user']['email']
            update_gchat_space(email, None)
    elif event['type'] == 'MESSAGE':
        text = "This is a one way street. I will completely ignore anything you type."

    if text:
        return JsonResponse({"text": text})
    else:
        return HttpResponse("OK")

@login_required
@require_http_methods(['POST'])
def upvote_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    post.upvote(request.user)
    return HttpResponse('OK')

@login_required
@require_http_methods(['POST'])
def downvote_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    post.downvote(request.user)
    return HttpResponse('OK')

@login_required
@require_http_methods(['POST'])
def undo_vote_on_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    post.undo_vote(request.user)
    return HttpResponse('OK')

@login_required
@require_http_methods(['POST'])
def upvote_comment(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    comment.upvote(request.user)
    return HttpResponse('OK')

@login_required
@require_http_methods(['POST'])
def downvote_comment(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    comment.downvote(request.user)
    return HttpResponse('OK')

@login_required
@require_http_methods(['POST'])
def undo_vote_on_comment(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    comment.undo_vote(request.user)
    return HttpResponse('OK')

@login_required
def myprofile(request):
    return render(request, "profile.html", context={})

def profile(request, userid):
    return render(request, "profile.html", context={"user": {"id": userid}})
