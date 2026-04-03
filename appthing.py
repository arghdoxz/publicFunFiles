"""
Kivy starter template for practice.

Run with:
	python appthing.py
"""

# Core Kivy app class
from kivy.app import App

# Basic UI widgets and layout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput


class PracticeApp(App):
	"""A small starter app to practice Kivy fundamentals."""

	def build(self):
		# App state: we store values on self so multiple methods can access them.
		self.count = 0

		# Root layout arranges widgets from top to bottom.
		root = BoxLayout(
			orientation="vertical",
			padding=20,
			spacing=12,
		)

		# Title at the top.
		title = Label(
			text="Kivy Practice Starter",
			font_size=30,
			size_hint=(1, 0.2),
		)

		# Text input where you can type your name.
		self.name_input = TextInput(
			hint_text="Type your name here",
			multiline=False,
			size_hint=(1, 0.15),
		)

		# Status label changes based on user actions.
		self.status_label = Label(
			text="Press the button to start.",
			font_size=22,
			size_hint=(1, 0.25),
		)

		# Button that triggers an event callback.
		action_button = Button(
			text="Click Me",
			font_size=24,
			size_hint=(1, 0.2),
		)

		# Event binding: when pressed, call self.on_click.
		action_button.bind(on_press=self.on_click)

		# Add widgets to root in display order.
		root.add_widget(title)
		root.add_widget(self.name_input)
		root.add_widget(self.status_label)
		root.add_widget(action_button)

		# build() must return the root widget.
		return root

	def on_click(self, _instance):
		# Update app state each time the button is pressed.
		self.count += 1

		# Read and sanitize user input.
		name = self.name_input.text.strip() or "friend"

		# Show the new state in the UI.
		self.status_label.text = f"Hi {name}, button clicks: {self.count}"


if __name__ == "__main__":
	# App entry point.
	PracticeApp().run()
