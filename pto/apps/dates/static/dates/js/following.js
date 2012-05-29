var AutocompleteUser = (function() {
  return {
     init: function(input_id, remote_url) {
       $('#' + input_id)
         // don't navigate away from the field on tab when selecting an item
         .bind( "keydown", function( event ) {
           if ( event.keyCode === $.ui.keyCode.TAB &&
                $( this ).data( "autocomplete" ).menu.active ) {
             event.preventDefault();
           }
         })
           .autocomplete({
              source: remote_url,
             select: function( event, ui ) {
               if (this.value) {
                 $(this).parent('form').submit();
               }
             }
           });
     }
  }
})();

var FollowingLists = (function() {
  return {
     add_observed: function(name, id, reason) {
       var tr = $('<tr>');
       $('<td>')
         .text(name)
         .appendTo(tr);
       $('<td>')
         .text(reason)
         .addClass('reason')
         .appendTo(tr);
       $('<td>')
         .append($('<a href="#">')
                 .text('remove')
                 .attr('data-id', id)
                 .addClass('remove')
                 .click(function() {
                   FollowingLists.remove(this);
                   return false;
                 })
                )
         .appendTo(tr);
       tr.prependTo($('#observed table'));
       $('#not-observed a.restore').each(function(i, each) {
         if (id == parseInt($(each).attr('data-id'))) {
           $(each).parents('tr').remove();
         }
       });
     },
    add_not_observed: function(name, id) {
       var tr = $('<tr>');
       $('<td>')
         .text(name)
         .appendTo(tr);
       $('<td>')
         .append($('<a href="#">')
                 .text('restore')
                 .attr('data-id', id)
                 .addClass('restore')
                 .click(function() {
                   FollowingLists.restore(this);
                   return false;
                 })
                )
         .appendTo(tr);
       tr.prependTo($('#not-observed table'));
    },
    remove: function(element) {
      var form = $('#content form');
      var csrf = $('input[name="csrfmiddlewaretoken"]', form).val();
      $.ajax({
         url: form.attr('action') + 'unfollow/',
        data: {remove: $(element).attr('data-id'), csrfmiddlewaretoken: csrf},
        type: 'POST',
        success: function(response) {
          $(element).parents('tr').remove();
          if (response.name && response.id) {
            FollowingLists.add_not_observed(response.name, response.id);
          }
        }
      });

    },
    restore: function(element) {
      FollowingLists.add($(element).attr('data-id'), function() {
        $(element).parents('tr').remove();
      });
    },
    add: function(search, callback) {
      var form = $('#content form');
      var csrf = $('input[name="csrfmiddlewaretoken"]', form).val();
      $.ajax({
         url: form.attr('action'),
        data: {search: search, csrfmiddlewaretoken: csrf},
        type: 'POST',
        error: function(xhr, status, error_thrown) {
          var msg = status;
          if (xhr.responseText)
            msg += ': ' + xhr.responseText;
          alert(msg);
        },
        success: function(response) {
          if (response.name && response.id && response.reason) {
            FollowingLists.add_observed(response.name, response.id, response.reason);
          }
          if (callback) callback();
        }
      });
    }
  }
})();


$(function() {
  $('#content form').submit(function() {
    if (!$.trim($('#id_search').val())) return false;
    FollowingLists.add($('#id_search').val(), function() {
      $('#id_search').val('').focus();
    });
    return false;
  });

  $('a.remove').on('click', function() {
    FollowingLists.remove(this);
    return false;
  });

  $('a.restore').on('click', function() {
    FollowingLists.restore(this);
    return false;
  });

  AutocompleteUser.init('id_search', '/autocomplete/users/knownonly/');
});
