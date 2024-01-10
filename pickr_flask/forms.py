from itertools import combinations

from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, EqualTo, Length

DEFAULT_TOPICS = [""]


class SignupForm(FlaskForm):
    name = StringField(
        "Twitter/X Username",
        validators=[
            Length(min=4, max=32),
            DataRequired(),
        ],
    )
    name_check = StringField(
        "Confirm Twitter/X Username",
        validators=[
            Length(min=4, max=32),
            DataRequired(),
            EqualTo("name", message="usernames must match.")
        ],
    )

    email = StringField(
        "Email",
        validators=[
            Length(min=6),
            Email(message="Enter a valid email."),
            DataRequired(),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=8, message="Select a stronger password."),
        ],
    )
    confirm = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Register")


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(message="Enter a valid email.")],
    )
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log In")


class ResetForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(message="Enter your email.")],
    )
    submit = SubmitField("Reset password")

class BlogForm(FlaskForm):
    blog_input = TextAreaField('Create Content From Long Form Text', render_kw={"rows": 23, "cols": 100},validators=[
            Length(min=200, max=6000, message="Content must be longer than 200, and shorter than 6000 cahracters"),
            DataRequired(),
        ])
    submit = SubmitField("Create Posts From Content")

class PostForm(FlaskForm):
    post_input = TextAreaField('Create a post', render_kw={"rows": 7, "cols": 70},validators=[
            Length(min=1, max=280, message="Post must be shorter than 280 cahracters"),
            DataRequired(),
        ])
    submit = SubmitField("Create post and schedule")

class SetPasswordForm(FlaskForm):
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Set Password")


def all_different(strs):
    """Check strings are different."""
    return all(s1 != s2 for s1, s2 in combinations(strs, 2))


class TopicForm(FlaskForm):
    topic_1 = SelectField("Topics")
    topic_2 = SelectField("Topics")
    topic_3 = SelectField("Topics")

    custom_niche = StringField("Custom Niche", validators=[Length(max=50)])

    submit = SubmitField("Submit")

    def all_inputs(self):
        return [
            self.topic_1.data,
            self.topic_2.data,
            self.topic_3.data,
            #self.custom_niche.data,
        ]

    def nonempty_inputs(self):
        return list(
            filter(
                lambda x: x != "",
                self.all_inputs(),
            )
        )

    def validate(self, **kwargs):
        rv = FlaskForm.validate(self)
        if not rv:
            return False

        # check at least one input
        inputs = self.all_inputs()
        all_empty = all(t == "" for t in inputs)
        if all_empty:
            self.submit.errors.append("Please select at least one topic from the drop downs.")
            return False

        if not all_different(self.nonempty_inputs()):
            self.submit.errors.append(
                "Please select distinct topics for each field.",
            )
            return False

        return True
