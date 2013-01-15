/*jslint undef: true */
/*global document, $, fielddescriptions, Rule, window, setTimeout, properties: false */




//
// strip header, footer and stuff inside iframe
//
$(document).ready(function() {
    "use strict";

    if (window.top !== window.self) {
        $('body').css('padding-top', '0');
        $('#bootstrap-navbar').remove();
        $('#trac-before-subnav').remove();
        $('.subnav').remove();
        $('footer').remove();
    }
});



//
// retrieve navbar from pyramid
//
$(document).ready(function() {
    "use strict";

    if (window.top !== window.self) {
        // inside iframe, don't touch anything
        return;
    }

    $.get('/navbar',
          {},
          function(responseText, textStatus, jqXHR) {
              var $rt = $(responseText);

              /* TRAC DROPDOWN ON TOP */
              // attach the trac menu to the last left-aligned navigation menu
              $('#bootstrap-navbar').html($rt.find('div.navbar-inner'));
              $('#bootstrap-navbar .dropdown-toggle').dropdown();

              // replaces the footer and logo
              $('footer.footer').replaceWith($rt.find('footer.footer'));
          }
        );
});




//
// move the 'modify' link inside subnav
//
$(document).ready(function() {
    var $modify_link = $('a[href=#propertyform]');
    
    $modify_link.addClass('btn btn-info')
        .prepend(' ').prepend($('<i class="icon-white icon-pencil"></i>'))
        .appendTo('#modify-ticket-link-container');
    $modify_link.on('click', function() {
        // open the div
        $('#modify').parent().removeClass('collapsed');
        // process the click event as regular
        return true;
    });
});


//
// divide the 'modify' form fields that are only visible to developers
//
$(document).ready(function() {
    $('#modify .hidden-to-customers').first().before($('<hr>'));
});



//
// Move the "private comment" label in a more visible place
//
$(document).ready(function() {
    $('.private_comment_marker').each(function() {
        $(this).closest('h3').append($(this));
    });
});



$(document).ready(function() {
    "use strict";

    // TODO: spostare i caricamenti dinamici su wsgi ?
    
    var field, i, options;

    if (typeof Rule !== 'undefined') {
        var permissionrule = new Rule('PermissionRule'); // must match python class name exactly
    }
    
    
    for (field in fielddescriptions) {
        if (typeof properties !== 'undefined') {
            if (typeof properties[field] !== 'undefined') {
                options = properties[field].options;
                properties[field].options = [];
                for (i=0; i<options.length; i++) {
                    if (typeof options[i] === "object") {
                        properties[field].options.push(options[i]);
                    }
                    else {
                        var text = fielddescriptions[field][options[i]] || option;
                        // TODO: verificare 'name' and/or 'text' ???
                        properties[field].options.push({'value':options[i], 'name':text, 'text':text});
                    }
                }
            }
        }
        // ticket properties
        var selector = 'div[data-field-name="'+field+'"] a' ;
        // ticket form
        selector = selector + ", " + 'select#field-'+field+' option';
        // batchmodify form
        selector = selector + ", " + 'select#batchmod_value_'+field+' option';
        // ticket report
        selector = selector + ", " + 'table.tickets td.'+field;
        // custom query
        selector = selector + ", " + 'form#query select[name$="_'+field+'"] option';        
        // query results
        selector = selector + ", " + 'h2.report-result span[rel="'+field+'"]';
        $(selector).each(function() {
            var val = $.trim($(this).text());
            var newval = val && fielddescriptions[field][val];
            if (newval) {
                $(this).text(newval);
            }
        });
    }
    
});
// use js.chosen with customerrequest
//
$(document).ready(function() {
    $('#field-customerrequest').chosen()
});


