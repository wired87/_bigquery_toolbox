from django.urls import path

from dj.views.get_entries import BQGetTableDataView
from dj.views.upsert import BQBatchUpsertView

app_name = 'bq'
urlpatterns = [
    path('upsert/', BQBatchUpsertView.as_view()),
    path('get/', BQGetTableDataView.as_view()),
]
